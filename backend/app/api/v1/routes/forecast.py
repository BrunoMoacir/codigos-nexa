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

from fastapi import APIRouter, HTTPException, status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Engine & Processamento
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.etl import (
    TransactionIngestor,
    TransactionClassifier,
    RecurringDetector,
    run_shadow_invoice_detection
)
from app.cashflow import CashflowEngine
from app.schemas.forecast import ForecastResponse, build_forecast_response
from app.schemas.safe_to_spend import SafeToSpendResponse
from app.schemas.shadow_invoice import ShadowInvoiceListResponse
from app.etl.profiles import UserProfileAnalyzer

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/forecast", tags=["Forecast"])
logger = logging.getLogger(__name__)

# TODO: Conectar com banco de dados para buscar transações por user_id
# Por enquanto, vamos usar dados mock para testes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Buscar transações por usuário
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fetch_user_transactions(user_id: str, horizon_days: int = 30):
    """
    Busca transações do usuário e executa o pipeline financeiro.

    Estratégia:
      1. Tenta carregar dados REAIS do DuckDB (transactions_clean)
      2. Se não houver dados E APP_MODE=dev, usa MockPluggy (fallback)
      3. Em produção sem dados, retorna erro claro
    """
    import os

    logger.info(f"🔍 Buscando transações para user_id={user_id}")

    try:
        from app.runner import NexaRunner

        # ── 1. Tentar dados reais do DuckDB ──────────────────────
        runner = NexaRunner(mode="dev")  # mode não importa para run_from_db
        result = runner.run_from_db(user_id=user_id, horizon_days=horizon_days)

        if result is not None and result.get("status") == "success":
            logger.info("✅ Pipeline executado com dados REAIS do DuckDB para user=%s", user_id)
            return result

        # ── 2. Fallback: mock APENAS em dev ──────────────────────
        app_mode = os.getenv("APP_MODE", "dev")
        if app_mode == "dev":
            logger.warning(
                "⚠️ Sem dados reais para user=%s — usando Pluggy mock (APP_MODE=dev)",
                user_id,
            )
            runner_dev = NexaRunner(mode="dev")
            result = runner_dev.run(horizon_days=horizon_days)
            return result
        else:
            logger.error("❌ Sem dados reais para user=%s em modo PRODUÇÃO", user_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhum dado financeiro encontrado para o usuário {user_id}. "
                       "Conecte suas contas via Open Finance.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar transações: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar dados do usuário: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /forecast/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}", response_model=ForecastResponse)
async def get_forecast(
    user_id: str,
    horizon_days: int = 30
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
        logger.info(f"📊 Iniciando forecast para user_id={user_id} (horizon={horizon_days})...")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: BUSCAR DADOS DO USUÁRIO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        runner_result = await fetch_user_transactions(user_id, horizon_days=horizon_days)
        
        if not runner_result:
            logger.warning(f"⚠️ Nenhum dado encontrado para user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhum histórico financeiro encontrado para usuário {user_id}"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: EXTRAIR COMPONENTES DO RESULTADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        import polars as pl
        from app.etl.income_profiler import IncomeProfiler

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
            cashflow_data = {
                "starting_balance":  projections.get("current_balance", 0.0),
                "ending_balance":    ending_bal,
                "worst_balance":     worst_bal,
                "negative_day":      None if neg_days == 0 else "Sim",
                "risk_level":        safe_spend_data.get("risk_level", "LOW"),
                "total_shadow_impact": 0.0,
                "days_at_risk":      neg_days,
                "daily":             [],
            }
        else:
            cashflow_data = runner_result.get("cashflow", {})

        # ── Shadow Invoices ───────────────────────────────────────
        shadow_events = projections.get("shadow_events")
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

        if txns_df is not None and not txns_df.is_empty() and "amount" in txns_df.columns:
            # Get expense transactions (negative amounts) in last 90 days
            expense_df = txns_df.filter(pl.col("amount") < 0)
            if not expense_df.is_empty():
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
                        row["category"]
                        for row in cat_df.to_dicts()
                    ]

        if income_profile_obj is not None and hasattr(income_profile_obj, "to_dict"):
            income_profile_dict = income_profile_obj.to_dict()
            monthly_income   = income_profile_obj.monthly_net_income
            savings_rate = max(0.0, min(1.0, (monthly_income - monthly_expenses) / monthly_income)) if monthly_income > 0 else 0.0

            # income_ratio = expenses / income — o indicador correto de saúde de gasto
            # (burn_rate_ratio é a *taxa de consumo do orçamento no ritmo atual*, outro conceito)
            income_ratio = monthly_expenses / monthly_income if monthly_income > 0 else 1.0
            income_ratio = round(min(income_ratio, 1.0), 4)  # cap em 1.0 (nunca negativo)

            # ── 1. PROFILE TYPE — baseado em savings_rate ─────────────
            # savings_rate > 40% → POUPADOR
            # savings_rate 5–40% → EQUILIBRADO
            # savings_rate < 5%  → GASTADOR
            if savings_rate > 0.40:
                profile_type_calc = "POUPADOR"
            elif savings_rate >= 0.05:
                profile_type_calc = "EQUILIBRADO"
            else:
                profile_type_calc = "GASTADOR"

            # ── 2. HEALTH SCORE — savings_rate (70%) + gasto/renda (30%) ─
            # savings_rate: >=20% dá 70 pontos (pontuação máxima nessa frente)
            # income_ratio: quanto mais baixo melhor (expenses/income)
            savings_score  = min(70.0, savings_rate * 5.0 * 70.0)  # 0–70 pts
            spending_score = (1.0 - income_ratio) * 30.0           # 0–30 pts (0 se gasta = renda)
            health_score   = min(100, max(0, round(savings_score + spending_score)))

            # ── 3. TREND — baseado na estabilidade de renda histórica ────
            # 0.65 é um bom limiar para ESTÁVEL (renda PJ varia um pouco)
            income_stability = getattr(income_profile_obj, "income_stability", 1.0) or 0.0
            if income_stability >= 0.65:
                trend_calc = "ESTÁVEL"
            elif income_stability >= 0.4:
                trend_calc = "CRESCENTE"  # instável mas não crítico
            else:
                trend_calc = "DECRESCENTE"  # alta volatilidade

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
                "savings_rate":        round(savings_rate, 4),
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

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSTRUIR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        logger.info(f"✅ Forecast gerado com sucesso para user_id={user_id}")

        profile_type = profile_data.get("profile_type", "EQUILIBRADO")
        if profile_type not in ["CONSERVADOR", "EQUILIBRADO", "GASTADOR", "POUPADOR"]:
            profile_type = "EQUILIBRADO"

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
                "top_categories":      profile_data.get("top_categories", []),
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
        logger.error(f"❌ Erro inesperado ao gerar forecast: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar previsão financeira: {str(e)}"
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
