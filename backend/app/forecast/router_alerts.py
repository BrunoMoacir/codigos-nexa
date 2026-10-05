"""
app/api/v1/routes/alerts.py - Endpoint de Alertas Financeiros

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe GET /alerts/{user_id} que retorna alertas ativos:
    - Token expiry (T-30, T-7, T-0 dias)
    - Saldo negativo (quando vai ficar no vermelho)
    - Alto comprometimento de caixa (> 80%)
    - Assinaturas suspeitas

╔══════════════════════════════════════════════════════════════════════╗
║ TIPOS DE ALERTA                                                      ║
╚══════════════════════════════════════════════════════════════════════╝

1. TOKEN_EXPIRY (Consentimento vencendo)
   - Level: WARNING (T-30), CRITICAL (T-7, T-0)
   
2. NEGATIVE_BALANCE (Vai ficar negativo)
   - Level: CRITICAL
   
3. HIGH_COMMITMENT (Caixa muito comprometido)
   - Level: WARNING
   
4. SUSPICIOUS_SUBSCRIPTION (Gasto fora padrão)
   - Level: WARNING

5. DATA_QUALITY (Falta dados, confiança baixa)
   - Level: WARNING
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from app.core.security import require_owner
from pydantic import BaseModel, ConfigDict, Field
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/alerts", tags=["Alerts"])
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AlertItem(BaseModel):
    """Um alerta individual"""
    id: str = Field(..., description="ID único do alerta")
    type: str = Field(..., description="Tipo: TOKEN_EXPIRY, NEGATIVE_BALANCE, etc")
    level: str = Field(..., description="Severidade: INFO, WARNING, CRITICAL")
    title: str = Field(..., description="Título resumido")
    message: str = Field(..., description="Mensagem detalhada")
    due_date: datetime = Field(..., description="Data/hora do evento")
    action_url: str | None = Field(None, description="URL para ação (ex: /reconnect)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "alert_001",
            "type": "TOKEN_EXPIRY",
            "level": "CRITICAL",
            "title": "Conexão vence em 7 dias",
            "message": "Sua conexão com o Nubank vence em 7 dias. Reconecte para continuar recebendo dados.",
            "due_date": "2025-02-18T15:30:00Z",
            "action_url": "/api/v1/reconnect/user_123"
        }
    })


class AlertsResponse(BaseModel):
    """Resposta com lista de alertas"""
    user_id: str
    alerts: List[AlertItem]
    total_count: int
    critical_count: int
    warning_count: int
    generated_at: datetime

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_id": "user_123",
            "alerts": [],
            "total_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "generated_at": "2025-02-11T15:30:00Z"
        }
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS: Gerar alertas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _em_dias(n: int) -> str:
    """'amanhã' / 'em 1 dia' / 'em 5 dias' — o card dizia "em 1 dias"."""
    return "amanhã" if n == 1 else f"em {n} dias"


def generate_token_expiry_alerts(days_until_expiry: int) -> List[AlertItem]:
    """
    Gera alerta de expiração de token se necessário.
    
    Critérios:
    - T-30: WARNING
    - T-7: CRITICAL
    - T-0 ou vencido: CRITICAL
    """
    
    if days_until_expiry <= 0:
        return [AlertItem(
            id="token_expired",
            type="TOKEN_EXPIRY",
            level="CRITICAL",
            title="Conexão expirou",
            message="Sua conexão com o banco expirou. Reconecte imediatamente para continuar usando a Nexa.",
            due_date=datetime.now(timezone.utc),
            action_url="/connections"
        )]
    
    elif days_until_expiry <= 7:
        return [AlertItem(
            id="token_expiry_7d",
            type="TOKEN_EXPIRY",
            level="CRITICAL",
            title=f"Conexão vence {_em_dias(days_until_expiry)}",
            message=f"Sua conexão vence {_em_dias(days_until_expiry)}. Reconecte em breve para não perder acesso aos dados.",
            due_date=datetime.now(timezone.utc) + timedelta(days=days_until_expiry),
            action_url="/connections"
        )]
    
    elif days_until_expiry <= 30:
        return [AlertItem(
            id="token_expiry_30d",
            type="TOKEN_EXPIRY",
            level="WARNING",
            title=f"Conexão vence {_em_dias(days_until_expiry)}",
            message=f"Sua conexão vencerá {_em_dias(days_until_expiry)}. Planeje reconectar em breve.",
            due_date=datetime.now(timezone.utc) + timedelta(days=days_until_expiry),
            action_url="/connections"
        )]
    
    return []


# Consentimento Open Finance: validade máxima de 12 meses (Res. Conjunta
# BCB/CMN nº 1/2020). A conexão não guarda a data de expiração que a
# instituição informou, então a estimativa é pela data real da conexão.
_VALIDADE_CONSENTIMENTO_DIAS = 365


def alertas_de_consentimento(user_id: str) -> List[AlertItem]:
    """
    Alertas de vencimento a partir das conexões REAIS do usuário.

    Era `generate_token_expiry_alerts(30)` fixo: todo usuário — com ou sem
    banco conectado — recebia "Conexão vence em 30 dias". Era o único card que
    o feed mostrava para todos, e era falso.
    """
    try:
        from app.core.database import SessionLocal
        from app.core.models.pluggy_item import PluggyItem

        with SessionLocal() as db:
            itens = db.query(PluggyItem).filter(PluggyItem.user_id == user_id).all()
    except Exception as exc:
        logger.warning("alertas_de_consentimento(%s): %s", user_id, exc)
        return []

    hoje = datetime.now(timezone.utc)
    alertas: List[AlertItem] = []
    for item in itens:
        criado = item.created_at
        if criado is None:
            continue
        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)
        faltam = (criado + timedelta(days=_VALIDADE_CONSENTIMENTO_DIAS) - hoje).days
        for alerta in generate_token_expiry_alerts(faltam):
            banco = item.connector_name or "seu banco"
            alerta.id = f"{alerta.id}_{item.item_id}"
            alerta.title = alerta.title.replace("Conexão", f"Conexão com {banco}")
            alerta.message += " (estimativa pela data da conexão: o consentimento vale até 12 meses.)"
            alerta.action_url = "/connections"
            alertas.append(alerta)
    return alertas


def _id_estavel(user_id: str, alerta: AlertItem) -> str:
    """
    Id que sobrevive entre leituras: o mesmo alerta, o mesmo id.

    Os ids de anomalia eram o índice na lista (`anomaly_0_…`) — mudavam a
    cada leitura, e dispensar um alerta não tinha como valer para o próximo.
    """
    import hashlib

    base = f"{user_id}|{alerta.type}|{alerta.title}"
    if alerta.type == "SPENDING_ANOMALY":
        # Cada anomalia é UM lançamento, e várias têm o mesmo título ("Gasto
        # bem acima do normal"): só pelo título, três alertas saíam com o
        # mesmo id — chave duplicada na tela e "Dispensar" sumia com os três.
        base += f"|{alerta.message}"
    return f"{alerta.type.lower()}_{hashlib.sha256(base.encode()).hexdigest()[:12]}"


_TITULO_DA_ANOMALIA = {
    "UNUSUAL_AMOUNT": "Gasto bem acima do normal",
    "FREQUENCY_SPIKE": "Compras mais frequentes que o normal",
    "NEW_MERCHANT": "Gasto alto num lugar novo",
    "DUPLICATE_SUSPECT": "Possível cobrança em dobro",
}


def generate_negative_balance_alert(negative_day: int | None) -> List[AlertItem]:
    """
    Gera alerta se saldo vai ficar negativo nos próximos 30 dias.
    """
    
    if negative_day and negative_day > 0 and negative_day <= 30:
        return [AlertItem(
            id="negative_balance",
            type="NEGATIVE_BALANCE",
            level="CRITICAL",
            title=f"Saldo negativo {_em_dias(negative_day)}",
            message=f"Seu saldo pode ficar negativo {_em_dias(negative_day)} se manter os gastos atuais.",
            due_date=datetime.now(timezone.utc) + timedelta(days=negative_day),
            action_url=None
        )]
    
    return []


def generate_high_commitment_alert(
    safe_to_spend: float,
    current_balance: float,
    income_profile: Optional["IncomeProfile"] = None,
) -> List[AlertItem]:
    """
    Alerta se > 80% do caixa está comprometido com obrigações futuras.

    Quando income_profile disponível (confidence ≥ 0.5), enriquece a mensagem
    com o valor absoluto comprometido como % da renda mensal estimada (MI.6).
    """

    if current_balance <= 0:
        return []

    commitment_rate = 1 - (safe_to_spend / current_balance)

    if commitment_rate > 0.8:
        percentage = int(commitment_rate * 100)
        message = (
            f"{percentage}% de suas obrigações futuras já estão comprometidas. "
            f"Cuidado com novos gastos."
        )

        # MI.6: contextualiza com renda real quando disponível
        if (
            income_profile is not None
            and income_profile.confidence >= 0.5
            and income_profile.monthly_net_income > 0
        ):
            committed_amount = current_balance - safe_to_spend
            income_pct = committed_amount / income_profile.monthly_net_income * 100
            message += (
                f" Isso equivale a aproximadamente {income_pct:.0f}% "
                f"da sua renda mensal estimada "
                f"({brl(income_profile.monthly_net_income, 0)}/mês)."
            )

        return [AlertItem(
            id="high_commitment",
            type="HIGH_COMMITMENT",
            level="WARNING",
            title=f"{percentage}% do caixa comprometido",
            message=message,
            due_date=datetime.now(timezone.utc),
            action_url=None
        )]

    return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /alerts/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# `def` (não `async def`): o handler roda o pipeline do extrato, que é
# síncrono e pesado — dentro de `async def` ele travava o event loop e toda
# outra requisição do servidor esperava. Como `def`, vai para o threadpool.
@router.get("/{user_id}", response_model=AlertsResponse)
def get_alerts(user_id: str = Depends(require_owner)) -> AlertsResponse:
    """
    Retorna alertas ativos para o usuário.
    
    **Tipos de alerta gerados:**
    
    1. **TOKEN_EXPIRY** (Consentimento vencendo)
       - T-30: WARNING
       - T-7: CRITICAL
       - T-0+: CRITICAL
    
    2. **NEGATIVE_BALANCE** (Vai ficar negativo)
       - Quando: saldo vai virar negativo nos próximos 30 dias
       - Level: CRITICAL
    
    3. **HIGH_COMMITMENT** (Caixa muito comprometido)
       - Quando: >80% das obrigações futuras já estão
       - Level: WARNING
    
    4. **SUSPICIOUS_SUBSCRIPTION** (Gasto fora padrão)
       - Quando: assinatura nova ou mudança estranha
       - Level: WARNING
    
    **Retorna:**
    ```json
    {
        "user_id": "user_123",
        "alerts": [
            {
                "id": "alert_001",
                "type": "TOKEN_EXPIRY",
                "level": "CRITICAL",
                "title": "Conexão vence em 7 dias",
                "message": "...",
                "due_date": "2025-02-18T15:30:00Z",
                "action_url": "/api/v1/reconnect/user_123"
            }
        ],
        "total_count": 1,
        "critical_count": 1,
        "warning_count": 0,
        "generated_at": "2025-02-11T15:30:00Z"
    }
    ```
    
    **Fluxo Interno:**
    1. Buscar dados do usuário
    2. Checar token expiry
    3. Checar saldo negativo (forecast)
    4. Checar comprometimento de caixa
    5. Consolidar alertas
    """
    
    try:
        logger.info("🚨 Gerando alertas para user_id=%s", user_id)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: BUSCAR DADOS (via NexaRunner para teste)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        from app.runner import get_runner
        from app.forecast.etl.income_profiler import IncomeProfiler
        from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector
        import os
        import polars as pl
        from datetime import date as date_type

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"

        # O extrato DESTE usuário. Era `.run()` sem user_id: mock fixo da
        # Pluggy em dev, item sandbox novo em produção — os alertas nunca
        # falavam do dinheiro de quem os lia.
        runner_result = get_runner(mode).run_from_db(user_id, horizon_days=30) or {}

        # MI.6: Estimar renda a partir das transações para contextualizar alertas
        income_profile = None
        transactions_data = runner_result.get("transactions", {})
        transactions_df = transactions_data.get("pf_pj_classified_df")
        if transactions_df is not None and not transactions_df.is_empty():
            income_profile = IncomeProfiler().build(transactions_df)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: COLETAR ALERTAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        alerts: List[AlertItem] = []

        # ✅ ALERTA 1: Vencimento do consentimento, pelas conexões reais
        alerts.extend(alertas_de_consentimento(user_id))

        # ✅ ALERTA 2: Negative balance
        projections = runner_result.get("projections", {})
        cashflow_forecast = projections.get("cashflow_forecast")
        negative_day = None
        if cashflow_forecast is not None and not cashflow_forecast.is_empty():
            import polars as pl
            neg_days = cashflow_forecast.filter(pl.col("projected_balance") < 0)
            if not neg_days.is_empty():
                from datetime import date
                first_neg = neg_days.sort("date")[0]["date"][0]
                negative_day = (first_neg - date.today()).days
        alerts.extend(generate_negative_balance_alert(negative_day))

        # ✅ ALERTA 3: High commitment (com contexto de renda — MI.6)
        safe_to_spend_obj = projections.get("safe_to_spend")
        current_balance = projections.get("current_balance", 0)
        safe_to_spend_val = getattr(safe_to_spend_obj, "safe_to_spend_total", 0) if safe_to_spend_obj else 0
        alerts.extend(generate_high_commitment_alert(safe_to_spend_val, current_balance, income_profile))

        # ✅ ALERTA 4: Spending anomalies (MI.1 — ativa SpendingAnomalyDetector)
        if transactions_df is not None and not transactions_df.is_empty():
            today = date_type.today()
            cutoff_recent = today - timedelta(days=30)
            recent_df = transactions_df.filter(
                pl.col("transaction_date").cast(pl.Date) >= cutoff_recent
            )
            if not recent_df.is_empty():
                anomalies = SpendingAnomalyDetector().detect(
                    transactions_df=recent_df,
                    history_df=transactions_df,  # histórico completo (90 dias)
                    income_profile=income_profile,
                )
                _sev_map = {"ALERT": "CRITICAL", "WARNING": "WARNING", "INFO": "INFO"}
                for i, anomaly in enumerate(anomalies[:5]):  # limita a 5 por requisição
                    alerts.append(AlertItem(
                        id=f"anomaly_{i}_{anomaly.anomaly_type.lower()}",
                        type="SPENDING_ANOMALY",
                        level=_sev_map.get(anomaly.severity, "INFO"),
                        # era o nome interno em inglês ("Anomalia: Duplicate Suspect")
                        title=_TITULO_DA_ANOMALIA.get(
                            anomaly.anomaly_type, "Gasto fora do seu padrão"
                        ),
                        message=anomaly.description,
                        due_date=datetime.now(timezone.utc),
                        action_url=None,
                    ))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSOLIDAR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        for alerta in alerts:
            alerta.id = _id_estavel(user_id, alerta)
        alerts = _sem_dispensados(user_id, alerts)

        critical_count = sum(1 for a in alerts if a.level == "CRITICAL")
        warning_count = sum(1 for a in alerts if a.level == "WARNING")
        
        logger.info(
            f"✅ Alertas gerados",
            extra={
                "total": len(alerts),
                "critical": critical_count,
                "warning": warning_count
            }
        )
        
        return AlertsResponse(
            user_id=user_id,
            alerts=alerts,
            total_count=len(alerts),
            critical_count=critical_count,
            warning_count=warning_count,
            generated_at=datetime.now(timezone.utc)
        )
        
    except HTTPException:
        # 4xx/5xx intencionais (ex: 503 "Pluggy não configurada") devem
        # chegar ao cliente com status e mensagem originais — o handler
        # genérico abaixo os transformava em 500 opaco.
        raise
    except Exception as e:
        logger.error("Erro ao gerar alertas: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar alertas financeiros. Tente novamente.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: DELETE /alerts/{alert_id} (Marcar como lido)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DIAS_DISPENSADO = {"CRITICAL": 1, "WARNING": 7, "INFO": 14}


def _sem_dispensados(user_id: str, alerts: List[AlertItem]) -> List[AlertItem]:
    """Tira os alertas que o usuário dispensou há pouco (CRITICAL volta em 1 dia)."""
    if not alerts:
        return alerts
    try:
        from app.notifications.state_store import NotificationStateStore

        store = NotificationStateStore()
        con = store._conn()
        try:
            store._init(con)
            ids = [a.id for a in alerts]
            marcadores = ",".join("?" * len(ids))
            linhas = con.execute(
                "SELECT fingerprint, MAX(created_at) FROM notification_events "
                f"WHERE user_id = ? AND event_type = 'dismissed' AND fingerprint IN ({marcadores}) "
                "GROUP BY fingerprint",
                [user_id, *ids],
            ).fetchall()
        finally:
            con.close()
    except Exception as exc:
        logger.warning("Filtro de alertas dispensados indisponível: %s", exc)
        return alerts

    dispensados = {fp: quando for fp, quando in linhas}
    agora = datetime.now(timezone.utc)
    restantes = []
    for a in alerts:
        quando = dispensados.get(a.id)
        if quando is not None and quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        if quando is None or agora - quando > timedelta(days=_DIAS_DISPENSADO.get(a.level, 7)):
            restantes.append(a)
    return restantes


@router.delete("/{user_id}/{alert_id}")
def dismiss_alert(alert_id: str, user_id: str = Depends(require_owner)):
    """
    Dispensa um alerta: ele some de GET /alerts pelo período do nível
    (CRITICAL 1 dia, WARNING 7, INFO 14).

    Antes respondia "dismissed" sem gravar nada — o alerta voltava na leitura
    seguinte, e a interface não tinha como saber que o servidor mentira.
    """
    from app.notifications.state_store import NotificationStateStore

    NotificationStateStore().log_event(
        user_id=user_id,
        fingerprint=alert_id,
        notification_type="ALERT",
        event_type="dismissed",
    )
    logger.info("Alerta %s dispensado por %s", alert_id, user_id)
    return {
        "status": "dismissed",
        "alert_id": alert_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", tags=["Health"])
async def alerts_health():
    """Health check do serviço."""
    return {
        "status": "ok",
        "service": "alerts",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
