"""
app/schemas/forecast.py - Schemas para Previsões Financeiras

RESPONSABILIDADE:
    Schemas Pydantic para previsões financeiras, análises de tendências
    e projeções de longo prazo

INTEGRAÇÃO:
    - Usado pelos endpoints de forecast
    - Integra dados de Cashflow + Safe-to-Spend + Shadow Invoices
    - Retorna análise consolidada para dashboards

USAGE:
    from app.schemas.forecast import (
        ForecastResponse,
        FinancialHealthResponse,
        MonthlyForecastResponse
    )
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import date, datetime
from typing import Literal

from app.schemas.cashflow import CashflowSummaryResponse
from app.schemas.safe_to_spend import SafeToSpendResponse
from app.schemas.shadow_invoice import ShadowInvoiceListResponse


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ProfileType = Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
TrendType = Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FINANCIAL HEALTH (Saúde Financeira)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FinancialHealthResponse(BaseModel):
    """
    Análise de saúde financeira do usuário.
    
    Baseada no UserProfileAnalyzer do ETL.
    
    Attributes:
        profile_type: Tipo de perfil (CONSERVADOR/EQUILIBRADO/GASTADOR)
        health_score: Score de saúde financeira (0-100)
        savings_rate: Taxa de poupança (%)
        total_income: Receita total do período
        total_expenses: Despesa total do período
        monthly_avg_expenses: Média mensal de gastos
        top_categories: Top 3 categorias de gasto
        trend: Tendência dos gastos (CRESCENTE/ESTÁVEL/DECRESCENTE)
    
    Example:
        >>> health = FinancialHealthResponse(
        ...     profile_type="EQUILIBRADO",
        ...     health_score=75,
        ...     savings_rate=15.5,
        ...     total_income=51000.0,
        ...     total_expenses=43000.0,
        ...     monthly_avg_expenses=7166.67,
        ...     top_categories=["Alimentação", "Transporte", "Moradia"],
        ...     trend="ESTÁVEL"
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "profile_type": "EQUILIBRADO",
                "health_score": 75,
                "savings_rate": 15.5,
                "total_income": 51000.0,
                "total_expenses": 43000.0,
                "monthly_avg_expenses": 7166.67,
                "top_categories": ["Alimentação", "Transporte", "Moradia"],
                "trend": "ESTÁVEL"
            }
        }
    )
    
    profile_type: ProfileType = Field(
        ...,
        description="Tipo de perfil financeiro do usuário"
    )
    
    health_score: int = Field(
        ...,
        description="Score de saúde financeira (0-100)",
        ge=0,
        le=100
    )
    
    savings_rate: float = Field(
        ...,
        description="Taxa de poupança (%)",
        ge=-100.0,  # Pode ser negativo (gastando mais que ganha)
        le=100.0
    )
    
    total_income: float = Field(
        ...,
        description="Receita total do período analisado",
        ge=0.0
    )
    
    total_expenses: float = Field(
        ...,
        description="Despesa total do período analisado",
        ge=0.0
    )
    
    monthly_avg_expenses: float = Field(
        ...,
        description="Média mensal de gastos",
        ge=0.0
    )
    
    top_categories: list[str] = Field(
        ...,
        description="Top 3 categorias de gasto",
        max_length=10
    )
    
    trend: TrendType = Field(
        ...,
        description="Tendência dos gastos recentes"
    )

    # Campos adicionais (opcionais) — só presentes quando pipeline real é executado
    income_profile: dict = Field(
        default_factory=dict,
        description="Perfil de renda (IncomeProfiler): padrão, renda líquida, confiança"
    )

    burn_rate_alert: str = Field(
        default="NORMAL",
        description="Nível de alerta do burn rate (NORMAL / WARNING / CRITICAL)"
    )

    burn_rate_ratio: float = Field(
        default=0.0,
        description="Razão burn rate: total_expenses / monthly_income",
        ge=0.0
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MONTHLY FORECAST (Previsão Mensal)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MonthlyForecastResponse(BaseModel):
    """
    Previsão financeira para um mês específico.
    
    Attributes:
        month: Mês da previsão (1-12)
        year: Ano da previsão
        expected_income: Receita esperada
        expected_expenses: Despesa esperada
        expected_savings: Poupança esperada
        confidence: Confiança da previsão (0.0-1.0)
        risk_level: Nível de risco para o mês
    
    Example:
        >>> forecast = MonthlyForecastResponse(
        ...     month=3,
        ...     year=2026,
        ...     expected_income=8500.0,
        ...     expected_expenses=7200.0,
        ...     expected_savings=1300.0,
        ...     confidence=0.85,
        ...     risk_level="LOW"
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "month": 3,
                "year": 2026,
                "expected_income": 8500.0,
                "expected_expenses": 7200.0,
                "expected_savings": 1300.0,
                "confidence": 0.85,
                "risk_level": "LOW"
            }
        }
    )
    
    month: int = Field(
        ...,
        description="Mês da previsão (1-12)",
        ge=1,
        le=12
    )
    
    year: int = Field(
        ...,
        description="Ano da previsão",
        ge=2020,
        le=2100
    )
    
    expected_income: float = Field(
        ...,
        description="Receita esperada para o mês",
        ge=0.0
    )
    
    expected_expenses: float = Field(
        ...,
        description="Despesa esperada para o mês",
        ge=0.0
    )
    
    expected_savings: float = Field(
        ...,
        description="Poupança esperada (income - expenses)"
    )
    
    confidence: float = Field(
        ...,
        description="Confiança da previsão (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    
    risk_level: RiskLevel = Field(
        ...,
        description="Nível de risco para o mês"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORECAST RESPONSE (Resposta Consolidada)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ForecastResponse(BaseModel):
    """
    Resposta consolidada de forecast financeiro.
    
    Integra dados de múltiplos módulos do sistema:
        - Saúde financeira (UserProfileAnalyzer)
        - Projeção de cashflow (CashflowProjector)
        - Safe-to-spend (SafeToSpendCalculator)
        - Shadow invoices (Shadow Invoice Detection)
        - Previsões mensais (baseado em médias históricas)
    
    Attributes:
        user_id: ID do usuário
        generated_at: Data/hora de geração do forecast
        period_analyzed_days: Período histórico analisado (dias)
        financial_health: Análise de saúde financeira
        cashflow: Projeção de cashflow (30 dias)
        safe_to_spend: Cálculo de safe-to-spend
        shadow_invoices: Obrigações futuras detectadas
        monthly_forecasts: Previsões mensais (próximos 3-6 meses)
    
    Example:
        >>> forecast = ForecastResponse(
        ...     user_id="user123",
        ...     generated_at=datetime.now(),
        ...     period_analyzed_days=180,
        ...     financial_health=health,
        ...     cashflow=cashflow_summary,
        ...     safe_to_spend=sts_response,
        ...     shadow_invoices=shadow_list,
        ...     monthly_forecasts=[march, april, may]
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user123",
                "generated_at": "2026-02-06T14:30:00Z",
                "period_analyzed_days": 180,
                "financial_health": {
                    "profile_type": "EQUILIBRADO",
                    "health_score": 75,
                    "savings_rate": 15.5,
                    "total_income": 51000.0,
                    "total_expenses": 43000.0,
                    "monthly_avg_expenses": 7166.67,
                    "top_categories": ["Alimentação", "Transporte"],
                    "trend": "ESTÁVEL"
                },
                "cashflow": {
                    "horizon_days": 30,
                    "starting_balance": 5000.0,
                    "ending_balance": 3809.69,
                    "worst_balance": 3809.69,
                    "negative_day": None,
                    "risk_level": "LOW",
                    "total_shadow_impact": -1068.10,
                    "days_at_risk": 0
                },
                "safe_to_spend": {
                    "current_balance": 5000.0,
                    "min_projected_balance": 3809.69,
                    "total_shadow_invoices": -1068.10,
                    "safety_buffer": 200.0,
                    "safe_to_spend_total": 3609.69,
                    "safe_to_spend_daily": 120.32,
                    "days": 30,
                    "risk_level": "LOW"
                },
                "shadow_invoices": {
                    "invoices": [],
                    "total_count": 12,
                    "total_monthly_impact": -1068.10,
                    "subscriptions_count": 9,
                    "installments_count": 3
                },
                "monthly_forecasts": [
                    {
                        "month": 3,
                        "year": 2026,
                        "expected_income": 8500.0,
                        "expected_expenses": 7200.0,
                        "expected_savings": 1300.0,
                        "confidence": 0.85,
                        "risk_level": "LOW"
                    }
                ]
            }
        }
    )
    
    user_id: str = Field(
        ...,
        description="ID do usuário",
        min_length=1,
        max_length=100
    )
    
    generated_at: datetime = Field(
        ...,
        description="Data/hora de geração do forecast"
    )
    
    period_analyzed_days: int = Field(
        ...,
        description="Período histórico analisado (dias)",
        ge=1,
        le=730  # Máximo 2 anos
    )
    
    financial_health: FinancialHealthResponse = Field(
        ...,
        description="Análise de saúde financeira do usuário"
    )
    
    cashflow: CashflowSummaryResponse = Field(
        ...,
        description="Projeção de cashflow (resumo)"
    )
    
    safe_to_spend: SafeToSpendResponse = Field(
        ...,
        description="Cálculo de safe-to-spend"
    )
    
    shadow_invoices: ShadowInvoiceListResponse = Field(
        ...,
        description="Obrigações futuras detectadas"
    )
    
    monthly_forecasts: list[MonthlyForecastResponse] = Field(
        default_factory=list,
        description="Previsões mensais (próximos 3-6 meses)",
        max_length=12
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSOR: UserProfile (dataclass) → FinancialHealthResponse
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_user_profile_to_health(
    profile: "UserProfile"  # type: ignore (from app.etl.profiles)
) -> FinancialHealthResponse:
    """
    Converte UserProfile (dataclass do ETL) para FinancialHealthResponse.
    
    Args:
        profile: UserProfile retornado por UserProfileAnalyzer.analyze()
    
    Returns:
        FinancialHealthResponse pronto para serialização JSON
    
    Example:
        >>> from app.etl import UserProfileAnalyzer
        >>> 
        >>> analyzer = UserProfileAnalyzer()
        >>> profile = analyzer.analyze(df)
        >>> health = convert_user_profile_to_health(profile)
    """
    return FinancialHealthResponse(
        profile_type=profile.profile_type,
        health_score=profile.financial_health_score,
        savings_rate=profile.savings_rate,
        total_income=profile.total_income,
        total_expenses=profile.total_expenses,
        monthly_avg_expenses=profile.monthly_avg_expenses,
        top_categories=profile.top_categories,
        trend=profile.trend
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUILDER: ForecastResponse Consolidado
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_forecast_response(
    user_id: str,
    period_analyzed_days: int,
    financial_health: FinancialHealthResponse,
    cashflow: CashflowSummaryResponse,
    safe_to_spend: SafeToSpendResponse,
    shadow_invoices: ShadowInvoiceListResponse,
    monthly_forecasts: list[MonthlyForecastResponse] | None = None
) -> ForecastResponse:
    """
    Constrói ForecastResponse consolidado a partir de componentes.
    
    Helper function para simplificar criação do forecast completo.
    
    Args:
        user_id: ID do usuário
        period_analyzed_days: Período histórico analisado
        financial_health: Saúde financeira
        cashflow: Projeção de cashflow
        safe_to_spend: Safe-to-spend
        shadow_invoices: Obrigações futuras
        monthly_forecasts: Previsões mensais (opcional)
    
    Returns:
        ForecastResponse completo
    
    Example:
        >>> forecast = build_forecast_response(
        ...     user_id="user123",
        ...     period_analyzed_days=180,
        ...     financial_health=health,
        ...     cashflow=cashflow_summary,
        ...     safe_to_spend=sts,
        ...     shadow_invoices=shadows
        ... )
    """
    return ForecastResponse(
        user_id=user_id,
        generated_at=datetime.now(),
        period_analyzed_days=period_analyzed_days,
        financial_health=financial_health,
        cashflow=cashflow,
        safe_to_spend=safe_to_spend,
        shadow_invoices=shadow_invoices,
        monthly_forecasts=monthly_forecasts or []
    )