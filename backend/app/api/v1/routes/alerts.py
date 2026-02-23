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
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

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
            title="⛔ Conexão expirou",
            message="Sua conexão com o banco expirou. Reconecte imediatamente para continuar usando a Nexa.",
            due_date=datetime.now(timezone.utc),
            action_url="/api/v1/reconnect"
        )]
    
    elif days_until_expiry <= 7:
        return [AlertItem(
            id="token_expiry_7d",
            type="TOKEN_EXPIRY",
            level="CRITICAL",
            title=f"⚠️ Conexão vence em {days_until_expiry} dias",
            message=f"Sua conexão vence em {days_until_expiry} dias. Reconecte em breve para não perder acesso aos dados.",
            due_date=datetime.now(timezone.utc) + timedelta(days=days_until_expiry),
            action_url="/api/v1/reconnect"
        )]
    
    elif days_until_expiry <= 30:
        return [AlertItem(
            id="token_expiry_30d",
            type="TOKEN_EXPIRY",
            level="WARNING",
            title=f"⏰ Conexão vence em {days_until_expiry} dias",
            message=f"Sua conexão vencerá em {days_until_expiry} dias. Planeje reconectar em breve.",
            due_date=datetime.now(timezone.utc) + timedelta(days=days_until_expiry),
            action_url="/api/v1/reconnect"
        )]
    
    return []


def generate_negative_balance_alert(negative_day: int | None) -> List[AlertItem]:
    """
    Gera alerta se saldo vai ficar negativo nos próximos 30 dias.
    """
    
    if negative_day and negative_day > 0 and negative_day <= 30:
        return [AlertItem(
            id="negative_balance",
            type="NEGATIVE_BALANCE",
            level="CRITICAL",
            title=f"⛔ Saldo negativo em {negative_day} dias",
            message=f"Seu saldo pode ficar negativo em {negative_day} dias se manter os gastos atuais.",
            due_date=datetime.now(timezone.utc) + timedelta(days=negative_day),
            action_url=None
        )]
    
    return []


def generate_high_commitment_alert(safe_to_spend: float, current_balance: float) -> List[AlertItem]:
    """
    Alerta se > 80% do caixa está comprometido com obrigações futuras.
    """
    
    if current_balance <= 0:
        return []
    
    commitment_rate = 1 - (safe_to_spend / current_balance)
    
    if commitment_rate > 0.8:
        percentage = int(commitment_rate * 100)
        return [AlertItem(
            id="high_commitment",
            type="HIGH_COMMITMENT",
            level="WARNING",
            title=f"⚠️ {percentage}% do caixa comprometido",
            message=f"{percentage}% de suas obrigações futuras já estão comprometidas. Cuidado com novos gastos.",
            due_date=datetime.now(timezone.utc),
            action_url=None
        )]
    
    return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /alerts/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}", response_model=AlertsResponse)
async def get_alerts(user_id: str) -> AlertsResponse:
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
        logger.info(f"🚨 Gerando alertas para user_id={user_id}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: BUSCAR DADOS (via NexaRunner para teste)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        from app.runner import NexaRunner
        runner = NexaRunner(mode="dev")
        runner_result = runner.run(horizon_days=30)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: COLETAR ALERTAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        alerts: List[AlertItem] = []
        
        # ✅ ALERTA 1: Token expirity (placeholder - 30 dias no futuro)
        alerts.extend(generate_token_expiry_alerts(30))
        
        # ✅ ALERTA 2: Negative balance
        cashflow_data = runner_result.get("cashflow", {})
        negative_day = cashflow_data.get("negative_day")
        alerts.extend(generate_negative_balance_alert(negative_day))
        
        # ✅ ALERTA 3: High commitment
        safe_spend_data = runner_result.get("safe_to_spend", {})
        safe_to_spend = safe_spend_data.get("safe_to_spend_total", 0)
        current_balance = safe_spend_data.get("current_balance", 0)
        alerts.extend(generate_high_commitment_alert(safe_to_spend, current_balance))
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSOLIDAR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
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
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar alertas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar alertas: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: DELETE /alerts/{alert_id} (Marcar como lido)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.delete("/{user_id}/{alert_id}")
async def dismiss_alert(user_id: str, alert_id: str):
    """
    Marca um alerta como lido/ignorado.
    
    TODO: Implementar persistência no Postgres
    """
    
    logger.info(f"🔇 Ignorando alerta {alert_id} do user {user_id}")
    
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
