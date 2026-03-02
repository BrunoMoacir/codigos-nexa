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

async def fetch_user_transactions(user_id: str):
    """
    Busca transações do usuário no banco de dados.
    
    📌 TODO: Implementar query real no Postgres
    
    Por enquanto, retorna dados mock para teste.
    """
    logger.info(f"🔍 Buscando transações para user_id={user_id}")
    
    # ⚠️ PLACEHOLDER: Aqui entraria a query real no Postgres
    # SELECT * FROM transactions_clean WHERE user_id = ? AND date >= now() - interval 90 days
    
    # Por enquanto, usar NexaRunner para teste
    try:
        from app.runner import NexaRunner
        runner = NexaRunner(mode="dev")  # Usa Pluggy mock para teste
        
        # Executar pipeline completo (vai usar dados mock)
        logger.info("📊 Executando pipeline financeiro... (usando Pluggy mock)")
        result = runner.run(horizon_days=30)
        
        return result
        
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
        
        runner_result = await fetch_user_transactions(user_id)
        
        if not runner_result:
            logger.warning(f"⚠️ Nenhum dado encontrado para user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhum histórico financeiro encontrado para usuário {user_id}"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: EXTRAIR COMPONENTES DO RESULTADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Cashflow (projeção + safe-to-spend)
        cashflow_data = runner_result.get("cashflow", {})
        safe_spend_data = runner_result.get("safe_to_spend", {})

        # Shadow invoices (obrigações futuras)
        shadow_data = runner_result.get("shadow_invoices", {})

        # Financial health (análise de saúde)
        profile_data = runner_result.get("profile", {})

        # MI.7: Estimar income_profile a partir das transações para expor na resposta
        from app.etl.income_profiler import IncomeProfiler
        income_profile_dict: dict = {}
        transactions_data = runner_result.get("transactions", {})
        transactions_df_forecast = transactions_data.get("pf_pj_classified_df")
        if transactions_df_forecast is not None and not transactions_df_forecast.is_empty():
            income_profile_obj = IncomeProfiler().build(transactions_df_forecast)
            income_profile_dict = income_profile_obj.to_dict()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONVERTER PARA RESPONSE MODELS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 🔧 TODO: Implementar conversores de dict → Pydantic
        # Por enquanto, vamos retornar os dados como estão
        
        logger.info(f"✅ Forecast gerado com sucesso para user_id={user_id}")
        
        # Construir resposta consolidada
        # NOTA: A função build_forecast_response espera Response models
        # Como estamos com dados dict, retornamos diretamente como ForecastResponse
        
        # Mapear profile_type para valores válidos
        profile_type = profile_data.get("profile_type", "EQUILIBRADO")
        if profile_type not in ["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]:
            profile_type = "EQUILIBRADO"
        
        forecast_response = ForecastResponse(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc),
            period_analyzed_days=90,
            financial_health={
                "profile_type": profile_type,
                "health_score": profile_data.get("health_score", 50),
                "savings_rate": profile_data.get("savings_rate", 0.0),
                "total_income": profile_data.get("total_income", 0.0),
                "total_expenses": profile_data.get("total_expenses", 0.0),
                "monthly_avg_expenses": profile_data.get("monthly_avg_expenses", 0.0),
                "top_categories": profile_data.get("top_categories", []),
                "trend": profile_data.get("trend", "ESTÁVEL"),
                "income_profile": income_profile_dict,  # MI.7: renda filtrada e classificada
            },
            cashflow={
                "horizon_days": horizon_days,
                "starting_balance": cashflow_data.get("starting_balance", 0),
                "ending_balance": cashflow_data.get("ending_balance", 0),
                "worst_balance": cashflow_data.get("worst_balance", 0),
                "negative_day": cashflow_data.get("negative_day"),
                "risk_level": cashflow_data.get("risk_level", "LOW"),
                "total_shadow_impact": cashflow_data.get("total_shadow_impact", 0),
                "days_at_risk": cashflow_data.get("days_at_risk", 0),
                "daily_data": cashflow_data.get("daily", [])
            },
            safe_to_spend={
                "current_balance": safe_spend_data.get("current_balance", 0),
                "min_projected_balance": safe_spend_data.get("min_projected_balance", 0),
                "total_shadow_invoices": safe_spend_data.get("total_shadow_invoices", 0),
                "safety_buffer": safe_spend_data.get("safety_buffer", 0),
                "safe_to_spend_total": safe_spend_data.get("safe_to_spend_total", 0),
                "safe_to_spend_daily": safe_spend_data.get("safe_to_spend_daily", 0),
                "days": horizon_days,
                "risk_level": safe_spend_data.get("risk_level", "LOW")
            },
            shadow_invoices={
                "invoices": shadow_data.get("invoices", []),
                "total_count": shadow_data.get("total_count", 0),
                "total_monthly_impact": shadow_data.get("total_monthly_impact", 0),
                "subscriptions_count": shadow_data.get("subscriptions_count", 0),
                "installments_count": shadow_data.get("installments_count", 0)
            },
            monthly_forecasts=[]  # TODO: Implementar previsões mensais
        )
        
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
