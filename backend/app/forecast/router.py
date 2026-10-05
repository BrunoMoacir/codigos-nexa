"""
app/api/v1/routes/forecast.py - Endpoint de Previsão Financeira

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe GET /forecast/{user_id} que retorna previsão consolidada:
    - Daily cashflow (próximos 30 dias)
    - Safe-to-Spend (quanto pode gastar com segurança)
    - Shadow invoices (obrigações futuras detectadas)
    - Financial health (análise de saúde financeira)
    - Risk assessment (risco de ficar no vermelho)

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO                                                                ║
╚══════════════════════════════════════════════════════════════════════╝

GET /api/v1/forecast/user_123?horizon_days=30
        ↓
Buscar dados no storage (raw transactions)
        ↓
Executar pipeline:
  1. ETL (normalizar)
  2. Shadow Invoice (detectar obrigações)
  3. Cashflow Projector (simular 30 dias)
  4. Safe-to-Spend (calcular margem)
        ↓
Consolidar ForecastResponse
        ↓
Retornar JSON com tudo
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.security import require_owner
from app.core.cache import cache_response
from app.core.formatacao import brl

limiter = Limiter(key_func=get_remote_address)


def _perfil_e_score(
    analyzer_profile,
    *,
    savings_rate_pct: float,
    income: float,
    expenses: float,
) -> tuple[str, int]:
    """
    `(profile_type, health_score)` — SEMPRE pela régua do UserProfileAnalyzer.

    Quando o analyzer rodou, usa o resultado dele. Quando falhou, aplica os
    MESMOS métodos sobre os valores que sobraram, em vez de inventar uma
    segunda fórmula. É a diferença entre um fallback com menos informação e um
    fallback com outra régua: o segundo produzia 8 onde o oficial produzia 55.
    """
    if analyzer_profile is not None:
        return analyzer_profile.profile_type, analyzer_profile.financial_health_score

    from app.forecast.etl.profiles import UserProfileAnalyzer

    analyzer = UserProfileAnalyzer()
    return (
        analyzer._determine_profile_type(savings_rate_pct),
        analyzer._calculate_health_score(savings_rate_pct, expenses, income),
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Engine & Processamento
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.forecast.etl import (
    TransactionIngestor,
    TransactionClassifier,
    RecurringDetector,
)
from app.subscriptions.shadow_invoices.runner import run_shadow_invoice_detection
from app.forecast.cashflow import CashflowEngine
from app.forecast.schemas_forecast import ForecastResponse, build_forecast_response
from app.forecast.schemas_safe_to_spend import SafeToSpendResponse
from app.forecast.schemas_shadow_invoice import ShadowInvoiceListResponse
from app.forecast.etl.profiles import UserProfileAnalyzer

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/forecast", tags=["Forecast"])
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Buscar transações por usuário
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fetch_user_transactions(user_id: str, horizon_days: int = 30):
    """
    Busca transações do usuário e executa o pipeline financeiro.

    Estratégia:
      1. Tenta carregar dados REAIS do DuckDB (transactions_clean)
      2. Calcula o saldo atual somando todas as transações
      3. Executa o pipeline com o saldo real
    """
    import os

    logger.info("🔍 Buscando transações para user_id=%s", user_id)

    try:
        from app.runner import NexaRunner
        from app.core.db.queries import get_transactions_for_user

        # ── 1. Buscar transações do banco ──────
        transactions_df = get_transactions_for_user(user_id)

        if transactions_df.is_empty():
            logger.error("❌ Sem dados reais para user=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhum dado financeiro encontrado para o usuário {user_id}. "
                       "Conecte suas contas via Open Finance.",
            )

        # ── 2. Calcular saldo atual (soma de todas as transações) ──────
        if "amount" not in transactions_df.columns:
            logger.error("❌ Coluna 'amount' não encontrada nas transações")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao processar transações: estrutura de dados inválida"
            )

        current_balance = float(transactions_df.select("amount").sum().item())
        logger.info(f"💰 Saldo calculado para user={user_id}: {brl(current_balance)}")

        # ── 3. Executar pipeline com saldo real ──────
        runner = NexaRunner(mode="dev")
        result = runner.run_from_db(
            user_id=user_id,
            horizon_days=horizon_days,
            current_balance=current_balance
        )

        if result is not None and result.get("status") == "success":
            logger.info("✅ Pipeline executado com dados REAIS do banco para user=%s", user_id)
            return result

        logger.error("❌ Erro ao executar pipeline para user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar dados do usuário"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ Erro ao buscar transações para user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar dados do usuário.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /forecast/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def primeiro_dia_negativo(cashflow_df) -> tuple[int | None, str | None]:
    """
    (número do primeiro dia projetado com saldo negativo, data dele).

    O dia 1 é o primeiro da projeção (amanhã). `negative_day` era a string
    "Sim", e o ForecastResponse exige int: o endpoint dava 500 exatamente para
    quem vai ficar no vermelho — o usuário que mais precisa do aviso.
    """
    import polars as pl

    if cashflow_df is None or cashflow_df.is_empty() or "projected_balance" not in cashflow_df.columns:
        return None, None
    negativos = (
        cashflow_df.with_row_index("_dia")
        .filter(pl.col("projected_balance") < 0)
    )
    if negativos.is_empty():
        return None, None
    dia = int(negativos["_dia"][0]) + 1
    data = str(negativos["date"][0])[:10] if "date" in negativos.columns else None
    return dia, data


@router.get("/{user_id}", response_model=ForecastResponse)
@cache_response(prefix="forecast", ttl=900)  # 15 min
@limiter.limit("10/minute")
async def get_forecast(
    request: Request,
    user_id: str = Depends(require_owner),
    horizon_days: int = 30,
) -> ForecastResponse:
    """
    Retorna previsão financeira consolidada do usuário.
    
    **Parâmetros:**
    - `user_id`: ID único do usuário
    - `horizon_days`: Dias para projetar no futuro (padrão: 30)
    
    **Retorna:**
    ```json
    {
        "user_id": "user_123",
        "generated_at": "2025-02-11T15:30:00Z",
        "period_analyzed_days": 90,
        "financial_health": {
            "profile_type": "BALANCED",
            "health_score": 75,
            ...
        },
        "cashflow": {
            "horizon_days": 30,
            "starting_balance": 5000.0,
            "ending_balance": 3809.69,
            "negative_day": null,
            ...
        },
        "safe_to_spend": {
            "current_balance": 5000.0,
            "safe_to_spend_total": 3609.69,
            "safe_to_spend_daily": 120.32,
            ...
        },
        "shadow_invoices": {
            "total_count": 12,
            "total_monthly_impact": -1068.10,
            "invoices": [...]
        }
    }
    ```
    
    **Fluxo Interno:**
    1. Busca transações do usuário (Postgres → TODO)
    2. Executa ETL pipeline
    3. Detecta shadow invoices (obrigações futuras)
    4. Projeta cashflow 30 dias
    5. Calcula safe-to-spend
    6. Consolida tudo em ForecastResponse
    
    **Erros possíveis:**
    - 404: Usuário não encontrado
    - 500: Erro ao processar dados
    """
    
    try:
        logger.info("📊 Iniciando forecast para user_id=%s (horizon=%d)", user_id, horizon_days)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: BUSCAR DADOS DO USUÁRIO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        runner_result = await fetch_user_transactions(user_id, horizon_days=horizon_days)
        
        if not runner_result:
            logger.warning("⚠️ Nenhum dado encontrado para user_id=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhum histórico financeiro encontrado para usuário {user_id}"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: EXTRAIR COMPONENTES DO RESULTADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        import polars as pl
        from app.forecast.etl.income_profiler import IncomeProfiler

        projections   = runner_result.get("projections", {})
        analysis      = runner_result.get("analysis", {})
        transactions  = runner_result.get("transactions", {})

        # ── Safe-to-Spend ─────────────────────────────────────────
        # run_from_db() retorna objeto SafeToSpendResult; run() retorna dict
        sts_raw = projections.get("safe_to_spend")
        if sts_raw is not None and hasattr(sts_raw, "safe_to_spend_total"):
            safe_spend_data = {
                "current_balance":     projections.get("current_balance", 0.0),
                "min_projected_balance": projections.get("min_projected_balance", 0.0),
                "total_shadow_invoices": 0.0,
                "safety_buffer":       getattr(sts_raw, "safety_buffer", 0.0),
                "safe_to_spend_total": sts_raw.safe_to_spend_total,
                "safe_to_spend_daily": sts_raw.safe_to_spend_daily,
                "risk_level":          sts_raw.risk_level,
            }
        else:
            safe_spend_data = runner_result.get("safe_to_spend", {})

        # ── Cashflow ──────────────────────────────────────────────
        cashflow_df = projections.get("cashflow_forecast")
        if cashflow_df is not None and isinstance(cashflow_df, pl.DataFrame) and not cashflow_df.is_empty():
            ending_bal  = cashflow_df.select("projected_balance").tail(1).item()
            worst_bal   = cashflow_df.select("projected_balance").min().item()
            neg_days    = cashflow_df.filter(pl.col("projected_balance") < 0).height
            primeiro_negativo, data_negativa = primeiro_dia_negativo(cashflow_df)
            cashflow_data = {
                "starting_balance":  projections.get("current_balance", 0.0),
                "ending_balance":    ending_bal,
                "worst_balance":     worst_bal,
                "negative_day":      primeiro_negativo,
                "first_negative_date": data_negativa,
                "risk_level":        safe_spend_data.get("risk_level", "LOW"),
                "total_shadow_impact": 0.0,
                "days_at_risk":      neg_days,
                "daily":             [],
            }
        else:
            cashflow_data = runner_result.get("cashflow", {})

        # ── Shadow Invoices ───────────────────────────────────────
        shadow_events = projections.get("shadow_events")
        # Shadow events podem vir do runner ou estar vazios; se vazios, tentar detectar a partir
        # do DataFrame de transações retornado para garantir que a API sempre entregue agenda.
        if shadow_events is None or (isinstance(shadow_events, pl.DataFrame) and shadow_events.is_empty()):
            # Tentar detectar a partir das transações retornadas pelo runner
            try:
                tx_df = transactions.get("pf_pj_classified_df")
                if tx_df is not None and not tx_df.is_empty():
                    detected = run_shadow_invoice_detection(tx_df)
                    shadow_events = detected
            except Exception:
                shadow_events = shadow_events

        if shadow_events is not None and isinstance(shadow_events, pl.DataFrame) and not shadow_events.is_empty():
            # Serialize each shadow event into a dict for the API response
            invoices_list = []
            for row in shadow_events.to_dicts():
                invoices_list.append({
                    "type":           row.get("type", "unknown"),
                    "amount":         round(float(row.get("amount", 0)), 2),
                    "next_due_date":  str(row.get("next_due_date", "")),
                    "confidence":     round(float(row.get("confidence", 0)), 2),
                    "description":    (row.get("metadata") or {}).get("description", ""),
                })
            shadow_data = {
                "invoices":             invoices_list,
                "total_count":          len(shadow_events),
                "total_monthly_impact": -round(abs(float(shadow_events.select("amount").sum().item())), 2) if "amount" in shadow_events.columns else 0.0,
                "subscriptions_count":  shadow_events.filter(pl.col("type").str.to_uppercase() == "SUBSCRIPTION").height if "type" in shadow_events.columns else 0,
                "installments_count":   shadow_events.filter(pl.col("type").str.to_uppercase() == "INSTALLMENT").height if "type" in shadow_events.columns else 0,
            }
        else:
            shadow_data = runner_result.get("shadow_invoices", {})

        # ── Income Profile / Financial Health ─────────────────────
        income_profile_obj = analysis.get("income_profile")
        burn_rate_obj = analysis.get("burn_rate")

        # Compute real expenses + top categories from transactions DataFrame
        txns_df = transactions.get("pf_pj_classified_df")
        monthly_expenses = 0.0
        top_categories_list = []
        analyzer_profile = None

        try:
            analyzer_profile = UserProfileAnalyzer().analyze(
                txns_df,
                income_profile=income_profile_obj,
            )
        except Exception as profile_err:
            # WARNING, não debug: sem o analyzer o score cai no fallback e o
            # usuário vê um número calculado com menos informação. Isso tem
            # que aparecer no log.
            logger.warning(
                "UserProfileAnalyzer falhou user=%s — health score irá pelo fallback: %s",
                user_id, profile_err,
            )

        if txns_df is not None and not txns_df.is_empty() and "amount" in txns_df.columns:
            # Get expense transactions (negative amounts) in last 90 days
            expense_df = txns_df.filter(pl.col("amount") < 0)
            if not expense_df.is_empty() and "transaction_date" in expense_df.columns:
                # Compute monthly average expenses from distinct months in data
                expense_with_month = expense_df.with_columns(
                    pl.col("transaction_date").dt.truncate("1mo").alias("_month")
                )
                n_months = expense_with_month.select("_month").n_unique()
                if n_months > 0:
                    monthly_expenses = abs(expense_df.select("amount").sum().item()) / n_months
                # Top categories by total absolute spend
                if "category" in txns_df.columns:
                    cat_df = (
                        expense_df
                        .group_by("category")
                        .agg(pl.col("amount").sum().abs().alias("total"))
                        .sort("total", descending=True)
                        .head(5)
                    )
                    top_categories_list = [
                        str(cat)
                        for row in cat_df.to_dicts()
                        if (cat := row.get("category"))
                    ]

        if income_profile_obj is not None and hasattr(income_profile_obj, "to_dict"):
            income_profile_dict = income_profile_obj.to_dict()
            monthly_income   = income_profile_obj.monthly_net_income
            # Fração, NÃO presa em zero. O clamp em [0, 1] fazia quem gasta mais
            # do que ganha aparecer poupando 0% — e, pela régua do analyzer
            # (poupança < 0 → 0 pontos, ≥ 0 → 20), ganhar 20 pontos de saúde
            # que não tem. O limite inferior de −1 é só a faixa do schema.
            savings_rate = max(-1.0, min(1.0, (monthly_income - monthly_expenses) / monthly_income)) if monthly_income > 0 else 0.0

            # income_ratio = expenses / income — o indicador correto de saúde de gasto
            # (burn_rate_ratio é a *taxa de consumo do orçamento no ritmo atual*, outro conceito)
            income_ratio = monthly_expenses / monthly_income if monthly_income > 0 else 1.0
            income_ratio = round(min(income_ratio, 1.0), 4)  # cap em 1.0 (nunca negativo)

            # ── 1 e 2. PROFILE TYPE e HEALTH SCORE ────────────────────
            #
            # FONTE ÚNICA: UserProfileAnalyzer. Havia aqui uma SEGUNDA fórmula
            # de health score — `savings_rate*5*70 + (1-income_ratio)*30` — que
            # divergia da oficial em até 47 pontos (poupança de 2%: 55 pela
            # oficial, 8 por esta). Ela era calculada e depois SOBRESCRITA
            # sempre que o analyzer funcionava, então só entrava em produção
            # quando `UserProfileAnalyzer().analyze()` levantava exceção — que
            # era engolida num `logger.debug`. Um erro silencioso mudava o
            # score do usuário em meia escala, sem sinal nenhum.
            #
            # O `profile_type` era pior: NUNCA era sobrescrito. O payload saía
            # com health_score do analyzer e profile_type de outra régua
            # (POUPADOR acima de 40%, EQUILIBRADO a partir de 5%), enquanto o
            # analyzer usa CONSERVADOR ≥20% / EQUILIBRADO ≥10% / GASTADOR. Uma
            # poupança de 22% saía como "EQUILIBRADO" com score de
            # "CONSERVADOR".
            profile_type_calc, health_score = _perfil_e_score(
                analyzer_profile,
                savings_rate_pct=savings_rate * 100,
                income=monthly_income,
                expenses=monthly_expenses,
            )

            # ── 3. TREND — direção do GASTO, do analyzer ──────────────
            #
            # Vinha de `income_stability`: renda instável virava "CRESCENTE",
            # muito instável virava "DECRESCENTE". Em todo o resto do produto
            # essas palavras significam direção de GASTO (ver trend_detector),
            # e aqui carregavam volatilidade de RENDA com o mesmo nome.
            trend_calc = getattr(analyzer_profile, "trend", None) or "ESTÁVEL"

            # ── 4. BURN RATE ALERT — baseado em expenses / income ─────────
            # < 60% = NORMAL | 60-80% = ATTENTION | 80-100% = WARNING | > 100% = CRITICAL
            if income_ratio >= 1.0:
                burn_alert = "CRITICAL"
            elif income_ratio >= 0.80:
                burn_alert = "WARNING"
            elif income_ratio >= 0.60:
                burn_alert = "ATTENTION"
            else:
                burn_alert = "NORMAL"

            profile_data = {
                "profile_type":        profile_type_calc,
                "health_score":        health_score,
                # Porcentagem (−100 a 100), como o FinancialHealthResponse e o
                # /health-score/history declaram. Saía como fração (0,0968) num
                # e porcentagem (9,68) no outro, para a mesma usuária.
                "savings_rate":        round(savings_rate * 100, 2),
                "total_income":        round(monthly_income, 2),
                "total_expenses":      round(monthly_expenses, 2),
                "monthly_avg_expenses": round(monthly_expenses, 2),
                "top_categories":      top_categories_list,
                "trend":               trend_calc,
                # burn_rate: expõe income_ratio (expenses/income) — a métrica correta
                # burn_rate_ratio (pace ratio) fica disponível só para debug
                "burn_rate_alert":     burn_alert,
                "burn_rate_ratio":     round(income_ratio, 4),  # expenses/income, não pace ratio
            }
        else:
            income_profile_dict = {}
            profile_data = runner_result.get("profile", {})

        if analyzer_profile is not None and "health_score" not in profile_data:
            profile_data["health_score"] = analyzer_profile.financial_health_score

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSTRUIR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        logger.info("✅ Forecast gerado com sucesso para user_id=%s", user_id)

        profile_type = profile_data.get("profile_type", "EQUILIBRADO")
        if profile_type not in ["CONSERVADOR", "EQUILIBRADO", "GASTADOR", "POUPADOR"]:
            profile_type = "EQUILIBRADO"

        raw_top_categories = profile_data.get("top_categories", [])
        if not isinstance(raw_top_categories, list):
            raw_top_categories = []
        safe_top_categories = [
            (c if isinstance(c, str) else str(c))
            for c in raw_top_categories
            if c is not None and str(c).strip() != ""
        ]

        forecast_response = ForecastResponse(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc),
            period_analyzed_days=90,
            financial_health={
                "profile_type":        profile_type,
                "health_score":        profile_data.get("health_score", 50),
                "savings_rate":        profile_data.get("savings_rate", 0.0),
                "total_income":        profile_data.get("total_income", 0.0),
                "total_expenses":      profile_data.get("total_expenses", 0.0),
                "monthly_avg_expenses": profile_data.get("monthly_avg_expenses", 0.0),
                "top_categories":      safe_top_categories,
                "trend":               profile_data.get("trend", "ESTÁVEL"),
                "income_profile":      income_profile_dict,
                "burn_rate_alert":     profile_data.get("burn_rate_alert", "NORMAL"),
                "burn_rate_ratio":     profile_data.get("burn_rate_ratio", 0.0),
            },

            cashflow={
                "horizon_days":        horizon_days,
                "starting_balance":    cashflow_data.get("starting_balance", 0),
                "ending_balance":      cashflow_data.get("ending_balance", 0),
                "worst_balance":       cashflow_data.get("worst_balance", 0),
                "negative_day":        cashflow_data.get("negative_day"),
                "risk_level":          cashflow_data.get("risk_level", "LOW"),
                "total_shadow_impact": cashflow_data.get("total_shadow_impact", 0),
                "days_at_risk":        cashflow_data.get("days_at_risk", 0),
                "first_negative_date": cashflow_data.get("first_negative_date"),
                "daily_data":          cashflow_data.get("daily", [])
            },
            safe_to_spend={
                "current_balance":      safe_spend_data.get("current_balance", 0),
                "min_projected_balance": safe_spend_data.get("min_projected_balance", 0),
                "total_shadow_invoices": safe_spend_data.get("total_shadow_invoices", 0),
                "safety_buffer":        safe_spend_data.get("safety_buffer", 0),
                "safe_to_spend_total":  safe_spend_data.get("safe_to_spend_total", 0),
                "safe_to_spend_daily":  safe_spend_data.get("safe_to_spend_daily", 0),
                "days":                 horizon_days,
                "risk_level":           safe_spend_data.get("risk_level", "LOW")
            },
            shadow_invoices={
                "invoices":             shadow_data.get("invoices", []),
                "total_count":          shadow_data.get("total_count", 0),
                "total_monthly_impact": shadow_data.get("total_monthly_impact", 0),
                "subscriptions_count":  shadow_data.get("subscriptions_count", 0),
                "installments_count":   shadow_data.get("installments_count", 0)
            },
            monthly_forecasts=[])
        
        return forecast_response
        
    except HTTPException:
        # Erros HTTP já formatados
        raise
    except Exception as e:
        logger.error("❌ Erro inesperado ao gerar forecast para user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar previsão financeira.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", tags=["Health"])
async def forecast_health():
    """
    Health check do serviço de forecast.
    
    Retorna:
    ```json
    {
        "status": "ok",
        "timestamp": "2025-02-11T15:30:00Z"
    }
    ```
    """
    return {
        "status": "ok",
        "service": "forecast",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
