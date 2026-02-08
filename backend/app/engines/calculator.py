"""
engines/calculator.py - Motor Unificado de Cálculos Financeiros

RESPONSABILIDADE:
    Orquestra os cálculos financeiros usando os módulos existentes de cashflow.

INTEGRAÇÃO:
    ✅ USA app.cashflow.projector.CashflowProjector (existente)
    ✅ USA app.cashflow.safe_to_spend.SafeToSpendCalculator (existente)
    ✅ USA app.domain.finance_engine.FinanceEngine (existente)

PRINCÍPIOS:
    ✅ NÃO reimplementa o que já existe
    ✅ Orquestra módulos existentes
    ✅ Adiciona validações rigorosas
    ✅ Logging estruturado para auditoria

USAGE:
    from app.engines.calculator import FinancialCalculator
    
    calculator = FinancialCalculator()
    
    # Safe-to-Spend
    sts = calculator.calculate_safe_to_spend(
        projection_df=cashflow_projection,
        horizon_days=30
    )
    
    # Cashflow
    projection = calculator.project_cashflow(
        transactions_df=df_clean,
        shadow_invoices_df=shadow_df,
        horizon_days=90
    )
    
    # Health Score
    health = calculator.calculate_health(
        transactions_df=df_clean,
        period_days=180
    )
"""

import logging
from datetime import date, datetime, timedelta
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field, field_validator

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS DOS MÓDULOS EXISTENTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Cashflow (USAR MÓDULOS EXISTENTES)
from app.cashflow.projector import CashflowProjector, ProjectionSummary
from app.cashflow.safe_to_spend import SafeToSpendCalculator, SafeToSpendResult

# Domain Engines (SE EXISTIR)
try:
    from app.domain.finance_engine import FinanceEngine
    HAS_FINANCE_ENGINE = True
except ImportError:
    HAS_FINANCE_ENGINE = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE MODELS (Re-export das classes existentes + novas)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Re-export das classes existentes
__all__ = [
    "SafeToSpendResult",      # de app.cashflow.safe_to_spend
    "ProjectionSummary",      # de app.cashflow.projector
    "FinancialCalculator",    # classe principal
]


class CashflowProjection(BaseModel):
    """
    Projeção completa de cashflow (wrapper).
    
    Encapsula ProjectionSummary + DataFrame em um único objeto.
    """
    
    summary: ProjectionSummary
    daily_projection: list[dict] = Field(description="Projeção dia a dia")
    
    class Config:
        arbitrary_types_allowed = True


class FinancialHealth(BaseModel):
    """Score de saúde financeira."""
    
    health_score: int = Field(ge=0, le=100, description="Score 0-100")
    profile_type: Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
    savings_rate: float = Field(ge=-100, le=100, description="Taxa de poupança (%)")
    total_income: float = Field(ge=0, description="Receita total no período")
    total_expenses: float = Field(ge=0, description="Despesa total no período")
    monthly_avg_expenses: float = Field(ge=0, description="Média mensal de gastos")
    top_categories: list[str] = Field(description="Top 3 categorias de gasto")
    trend: Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FINANCIAL CALCULATOR (Orquestrador)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FinancialCalculator:
    """
    Motor unificado de cálculos financeiros.
    
    ORQUESTRA (não reimplementa):
    - CashflowProjector (app.cashflow.projector)
    - SafeToSpendCalculator (app.cashflow.safe_to_spend)
    - FinanceEngine (app.domain.finance_engine)
    
    ADICIONA:
    - Validações rigorosas
    - Logging estruturado
    - API unificada
    """
    
    def __init__(self, safety_buffer_pct: float = 0.15):
        """
        Inicializa o calculador.
        
        Args:
            safety_buffer_pct: Buffer de segurança (default: 15%)
        """
        self.safety_buffer_pct = safety_buffer_pct
        
        # Inicializar módulos existentes
        self.cashflow_projector = CashflowProjector(horizon_days=30)
        self.safe_to_spend_calculator = SafeToSpendCalculator(
            safety_buffer_pct=safety_buffer_pct
        )
        
        if HAS_FINANCE_ENGINE:
            self.finance_engine = FinanceEngine()
        
        logger.info(f"FinancialCalculator initialized with buffer={safety_buffer_pct*100:.1f}%")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. SAFE-TO-SPEND (usa SafeToSpendCalculator existente)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def calculate_safe_to_spend(
        self,
        projection_df: pl.DataFrame,
        horizon_days: int = 30
    ) -> SafeToSpendResult:
        """
        Calcula quanto o usuário pode gastar com segurança.
        
        DELEGA para: app.cashflow.safe_to_spend.SafeToSpendCalculator
        
        Args:
            projection_df: DataFrame com projeção de cashflow
                Colunas obrigatórias:
                - date (date)
                - projected_balance (float)
                - expenses (float)
                - risk_flag (bool|None)
            horizon_days: Horizonte de projeção (1-365)
        
        Returns:
            SafeToSpendResult
        
        Example:
            >>> calculator = FinancialCalculator()
            >>> result = calculator.calculate_safe_to_spend(
            ...     projection_df=cashflow_df,
            ...     horizon_days=30
            ... )
            >>> print(f"Você pode gastar R$ {result.safe_to_spend_daily:.2f}/dia")
        """
        logger.info(f"Calculating safe-to-spend for horizon_days={horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if projection_df.is_empty():
            raise ValueError("projection_df cannot be empty")
        
        required_cols = ["date", "projected_balance", "expenses"]
        missing_cols = [col for col in required_cols if col not in projection_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        if not (1 <= horizon_days <= 365):
            raise ValueError(f"horizon_days must be 1-365, got {horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # DELEGAR PARA MÓDULO EXISTENTE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        result = self.safe_to_spend_calculator.calculate(
            projection_df=projection_df,
            horizon_days=horizon_days
        )
        
        logger.info(
            f"Safe-to-Spend calculated: "
            f"daily=R${result.safe_to_spend_daily:.2f}, "
            f"risk={result.risk_level}"
        )
        
        return result
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. CASHFLOW PROJECTION (usa CashflowProjector existente)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def project_cashflow(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame | None = None,
        horizon_days: int = 30
    ) -> CashflowProjection:
        """
        Projeta saldo futuro dia a dia.
        
        DELEGA para: app.cashflow.projector.CashflowProjector
        
        Args:
            transactions_df: Transações históricas (com coluna 'balance')
            shadow_invoices_df: Despesas futuras projetadas (opcional)
            horizon_days: Quantos dias projetar (1-365)
        
        Returns:
            CashflowProjection com summary + daily_projection
        
        Example:
            >>> projection = calculator.project_cashflow(
            ...     transactions_df=df_with_balance,
            ...     shadow_invoices_df=shadow_df,
            ...     horizon_days=90
            ... )
            >>> print(projection.summary.worst_balance)
        """
        logger.info(f"Projecting cashflow for horizon_days={horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("transactions_df cannot be empty")
        
        if "balance" not in transactions_df.columns:
            raise ValueError("transactions_df must have 'balance' column")
        
        if not (1 <= horizon_days <= 365):
            raise ValueError(f"horizon_days must be 1-365, got {horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # DELEGAR PARA MÓDULO EXISTENTE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Atualizar horizon_days
        self.cashflow_projector.horizon_days = horizon_days
        
        # Projetar
        if shadow_invoices_df is None:
            shadow_invoices_df = pl.DataFrame()
        
        projection_df = self.cashflow_projector.project(
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df
        )
        
        # Calcular resumo
        last_balance = float(transactions_df["balance"][-1])
        summary = self.cashflow_projector.get_summary(projection_df, last_balance)
        
        # Converter DataFrame para lista de dicts
        daily_projection = projection_df.to_dicts()
        
        logger.info(
            f"Cashflow projected: "
            f"starting={summary.starting_balance:.2f}, "
            f"ending={summary.ending_balance:.2f}, "
            f"risk={summary.risk_level}"
        )
        
        return CashflowProjection(
            summary=summary,
            daily_projection=daily_projection
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. FINANCIAL HEALTH (usa FinanceEngine existente ou implementa)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def calculate_health(
        self,
        transactions_df: pl.DataFrame,
        period_days: int = 180
    ) -> FinancialHealth:
        """
        Calcula score de saúde financeira (0-100).
        
        Args:
            transactions_df: Transações históricas
            period_days: Período de análise (default: 180 dias)
        
        Returns:
            FinancialHealth com score e métricas
        
        Example:
            >>> health = calculator.calculate_health(
            ...     transactions_df=df_categorized,
            ...     period_days=180
            ... )
            >>> print(f"Health Score: {health.health_score}/100")
        """
        logger.info(f"Calculating financial health for period_days={period_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("transactions_df cannot be empty")
        
        if "amount" not in transactions_df.columns:
            raise ValueError("transactions_df must have 'amount' column")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CALCULAR MÉTRICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Receita total (créditos)
        total_income = float(
            transactions_df.filter(pl.col("amount") > 0)["amount"].sum()
        )
        
        # Despesa total (débitos)
        total_expenses = float(
            abs(transactions_df.filter(pl.col("amount") < 0)["amount"].sum())
        )
        
        # Taxa de poupança
        if total_income > 0:
            savings_rate = ((total_income - total_expenses) / total_income) * 100
        else:
            savings_rate = -100.0
        
        # Média mensal
        months = period_days / 30
        monthly_avg_expenses = total_expenses / months if months > 0 else 0
        
        # Top categorias
        top_categories = []
        if "predicted_category" in transactions_df.columns:
            top_cats = (
                transactions_df
                .filter(pl.col("amount") < 0)
                .group_by("predicted_category")
                .agg(pl.col("amount").sum().alias("total"))
                .sort("total")
                .head(3)
            )
            top_categories = [row["predicted_category"] for row in top_cats.iter_rows(named=True)]
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PERFIL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if savings_rate > 20:
            profile_type = "CONSERVADOR"
        elif savings_rate > 5:
            profile_type = "EQUILIBRADO"
        else:
            profile_type = "GASTADOR"
        
        # Tendência (simplificado)
        trend = "ESTÁVEL"
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SCORE (0-100)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        base_score = max(0, min(100, (savings_rate + 20) * 2.5))
        
        score = base_score
        if total_expenses > total_income * 0.9:
            score -= 10
        if savings_rate > 30:
            score += 10
        
        health_score = int(max(0, min(100, score)))
        
        logger.info(
            f"Financial health: score={health_score}, "
            f"profile={profile_type}, savings_rate={savings_rate:.1f}%"
        )
        
        return FinancialHealth(
            health_score=health_score,
            profile_type=profile_type,
            savings_rate=round(savings_rate, 2),
            total_income=total_income,
            total_expenses=total_expenses,
            monthly_avg_expenses=monthly_avg_expenses,
            top_categories=top_categories,
            trend=trend
        )

    """Resultado do cálculo de Safe-to-Spend."""
    
    safe_to_spend_total: float = Field(ge=0, description="Quanto pode gastar no período")
    safe_to_spend_daily: float = Field(ge=0, description="Quanto pode gastar por dia")
    current_balance: float = Field(description="Saldo atual")
    min_projected_balance: float = Field(description="Menor saldo projetado")
    total_shadow_invoices: float = Field(le=0, description="Impacto de shadow invoices")
    safety_buffer: float = Field(ge=0, description="Buffer de segurança aplicado")
    safety_buffer_pct: float = Field(ge=0, le=1, description="Percentual do buffer")
    days: int = Field(ge=1, le=365, description="Horizonte de dias")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        description="Nível de risco financeiro"
    )
    recommendations: list[str] = Field(default_factory=list, description="Recomendações")
    
    @field_validator("total_shadow_invoices")
    @classmethod
    def shadow_must_be_negative_or_zero(cls, v):
        """Shadow invoices devem ser negativos (despesas) ou zero."""
        if v > 0:
            raise ValueError("Shadow invoices should be <= 0 (expenses)")
        return v


class CashflowSummary(BaseModel):
    """Resumo da projeção de cashflow."""
    
    horizon_days: int = Field(ge=1, le=365, description="Período projetado")
    starting_balance: float = Field(description="Saldo inicial")
    ending_balance: float = Field(description="Saldo final projetado")
    worst_balance: float = Field(description="Menor saldo no período")
    negative_day: int | None = Field(default=None, description="Primeiro dia negativo")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    total_shadow_impact: float = Field(le=0, description="Impacto total de shadows")
    days_at_risk: int = Field(ge=0, description="Dias com saldo crítico")


class CashflowProjection(BaseModel):
    """Projeção completa de cashflow."""
    
    summary: CashflowSummary
    daily_projection: list[dict] = Field(description="Projeção dia a dia")
    
    class Config:
        arbitrary_types_allowed = True


class FinancialHealth(BaseModel):
    """Score de saúde financeira."""
    
    health_score: int = Field(ge=0, le=100, description="Score 0-100")
    profile_type: Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
    savings_rate: float = Field(ge=-100, le=100, description="Taxa de poupança (%)")
    total_income: float = Field(ge=0, description="Receita total no período")
    total_expenses: float = Field(ge=0, description="Despesa total no período")
    monthly_avg_expenses: float = Field(ge=0, description="Média mensal de gastos")
    top_categories: list[str] = Field(description="Top 3 categorias de gasto")
    trend: Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FINANCIAL CALCULATOR (Motor Unificado)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FinancialCalculator:
    """
    Motor unificado de cálculos financeiros.
    
    Consolida:
    - Safe-to-Spend (quanto posso gastar?)
    - Cashflow Projection (projeção de saldo)
    - Financial Health (score 0-100)
    
    DESIGN PRINCIPLES:
    - Matemática pura (sem LLM)
    - Validações rigorosas
    - Logging estruturado
    - Confidence scores
    """
    
    def __init__(self, safety_buffer_pct: float = 0.15):
        """
        Inicializa o calculador.
        
        Args:
            safety_buffer_pct: Buffer de segurança (default: 15%)
        """
        self.safety_buffer_pct = safety_buffer_pct
        logger.info(f"FinancialCalculator initialized with buffer={safety_buffer_pct*100:.1f}%")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. SAFE-TO-SPEND CALCULATOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def calculate_safe_to_spend(
        self,
        projection_df: pl.DataFrame,
        horizon_days: int = 30
    ) -> SafeToSpendResult:
        """
        Calcula quanto o usuário pode gastar com segurança.
        
        METODOLOGIA:
        1. Identifica menor saldo projetado
        2. Calcula impacto de shadow invoices
        3. Aplica buffer de segurança (15%)
        4. Determina risk level
        5. Gera recomendações
        
        Args:
            projection_df: DataFrame com projeção de cashflow
                Colunas obrigatórias:
                - date (date)
                - projected_balance (float)
                - expenses (float)
                - risk_flag (bool|None)
            horizon_days: Horizonte de projeção (1-365)
        
        Returns:
            SafeToSpendResult com cálculo completo
        
        Raises:
            ValueError: Se inputs inválidos
        
        Example:
            >>> calculator = FinancialCalculator()
            >>> result = calculator.calculate_safe_to_spend(
            ...     projection_df=cashflow_df,
            ...     horizon_days=30
            ... )
            >>> print(f"Você pode gastar R$ {result.safe_to_spend_daily:.2f}/dia")
        """
        logger.info(f"Calculating safe-to-spend for horizon_days={horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if projection_df.is_empty():
            raise ValueError("projection_df cannot be empty")
        
        required_cols = ["date", "projected_balance", "expenses"]
        missing_cols = [col for col in required_cols if col not in projection_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        if not (1 <= horizon_days <= 365):
            raise ValueError(f"horizon_days must be 1-365, got {horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CÁLCULOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Saldo atual (primeiro dia da projeção)
        current_balance = float(projection_df["projected_balance"][0])
        
        # Menor saldo projetado
        min_projected_balance = float(projection_df["projected_balance"].min())
        
        # Impacto de shadow invoices (soma de despesas projetadas)
        total_shadow_invoices = float(
            projection_df.filter(pl.col("expenses") < 0)["expenses"].sum()
        )
        
        # Buffer de segurança (% do menor saldo)
        safety_buffer = abs(min_projected_balance) * self.safety_buffer_pct
        
        # Safe-to-Spend = Saldo Atual - Menor Saldo - Buffer
        safe_to_spend_total = current_balance - min_projected_balance - safety_buffer
        safe_to_spend_total = max(0, safe_to_spend_total)  # Nunca negativo
        
        # Safe-to-Spend diário
        safe_to_spend_daily = safe_to_spend_total / horizon_days
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RISK LEVEL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        risk_level = self._calculate_risk_level(
            min_projected_balance=min_projected_balance,
            current_balance=current_balance
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RECOMENDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        recommendations = self._generate_recommendations(
            risk_level=risk_level,
            safe_to_spend_daily=safe_to_spend_daily,
            total_shadow_invoices=total_shadow_invoices
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOGGING
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info(
            f"Safe-to-Spend calculated: "
            f"daily=R${safe_to_spend_daily:.2f}, "
            f"risk={risk_level}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RETORNO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return SafeToSpendResult(
            safe_to_spend_total=safe_to_spend_total,
            safe_to_spend_daily=safe_to_spend_daily,
            current_balance=current_balance,
            min_projected_balance=min_projected_balance,
            total_shadow_invoices=total_shadow_invoices,
            safety_buffer=safety_buffer,
            safety_buffer_pct=self.safety_buffer_pct,
            days=horizon_days,
            risk_level=risk_level,
            recommendations=recommendations
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. CASHFLOW PROJECTOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def project_cashflow(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame | None = None,
        horizon_days: int = 30
    ) -> CashflowProjection:
        """
        Projeta saldo futuro dia a dia.
        
        METODOLOGIA:
        1. Parte do último saldo conhecido
        2. Aplica shadow invoices nas datas projetadas
        3. Identifica dias de risco
        4. Calcula métricas de resumo
        
        Args:
            transactions_df: Transações históricas (com coluna 'balance')
            shadow_invoices_df: Despesas futuras projetadas (opcional)
            horizon_days: Quantos dias projetar (1-365)
        
        Returns:
            CashflowProjection com summary + daily_projection
        
        Example:
            >>> projection = calculator.project_cashflow(
            ...     transactions_df=df_with_balance,
            ...     shadow_invoices_df=shadow_df,
            ...     horizon_days=90
            ... )
            >>> print(projection.summary.worst_balance)
        """
        logger.info(f"Projecting cashflow for horizon_days={horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("transactions_df cannot be empty")
        
        if "balance" not in transactions_df.columns:
            raise ValueError("transactions_df must have 'balance' column")
        
        if not (1 <= horizon_days <= 365):
            raise ValueError(f"horizon_days must be 1-365, got {horizon_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SALDO INICIAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Último saldo conhecido
        starting_balance = float(transactions_df["balance"][-1])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PROJEÇÃO DIA A DIA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        today = date.today()
        daily_projection = []
        current_balance = starting_balance
        total_shadow_impact = 0.0
        
        for day_offset in range(horizon_days):
            projection_date = today + timedelta(days=day_offset + 1)
            
            # Buscar shadow invoices para este dia
            day_expenses = 0.0
            if shadow_invoices_df is not None and not shadow_invoices_df.is_empty():
                shadows_today = shadow_invoices_df.filter(
                    pl.col("next_due_date").cast(pl.Date) == projection_date
                )
                if not shadows_today.is_empty():
                    day_expenses = float(shadows_today["amount"].sum())
                    total_shadow_impact += day_expenses
            
            # Aplicar despesa ao saldo
            current_balance += day_expenses  # day_expenses já é negativo
            
            # Detectar risco
            risk_flag = current_balance < 200  # Threshold de risco
            
            daily_projection.append({
                "date": projection_date,
                "projected_balance": round(current_balance, 2),
                "expenses": round(day_expenses, 2),
                "risk_flag": risk_flag
            })
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # MÉTRICAS DE RESUMO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        balances = [d["projected_balance"] for d in daily_projection]
        worst_balance = min(balances)
        ending_balance = balances[-1]
        
        # Primeiro dia negativo
        negative_day = None
        for i, bal in enumerate(balances, start=1):
            if bal < 0:
                negative_day = i
                break
        
        # Dias em risco (saldo < 200)
        days_at_risk = sum(1 for d in daily_projection if d["risk_flag"])
        
        # Risk level
        risk_level = self._calculate_risk_level(worst_balance, starting_balance)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOGGING
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info(
            f"Cashflow projected: "
            f"starting={starting_balance:.2f}, "
            f"ending={ending_balance:.2f}, "
            f"worst={worst_balance:.2f}, "
            f"risk={risk_level}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RETORNO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        summary = CashflowSummary(
            horizon_days=horizon_days,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            worst_balance=worst_balance,
            negative_day=negative_day,
            risk_level=risk_level,
            total_shadow_impact=total_shadow_impact,
            days_at_risk=days_at_risk
        )
        
        return CashflowProjection(
            summary=summary,
            daily_projection=daily_projection
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. FINANCIAL HEALTH CALCULATOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def calculate_health(
        self,
        transactions_df: pl.DataFrame,
        period_days: int = 180
    ) -> FinancialHealth:
        """
        Calcula score de saúde financeira (0-100).
        
        METODOLOGIA:
        1. Calcula receita e despesa total
        2. Calcula savings rate (% poupança)
        3. Identifica perfil (conservador/equilibrado/gastador)
        4. Analisa tendência (crescente/estável/decrescente)
        5. Gera score 0-100
        
        Args:
            transactions_df: Transações históricas
            period_days: Período de análise (default: 180 dias)
        
        Returns:
            FinancialHealth com score e métricas
        
        Example:
            >>> health = calculator.calculate_health(
            ...     transactions_df=df_categorized,
            ...     period_days=180
            ... )
            >>> print(f"Health Score: {health.health_score}/100")
        """
        logger.info(f"Calculating financial health for period_days={period_days}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("transactions_df cannot be empty")
        
        if "amount" not in transactions_df.columns:
            raise ValueError("transactions_df must have 'amount' column")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CÁLCULOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Receita total (créditos)
        total_income = float(
            transactions_df.filter(pl.col("amount") > 0)["amount"].sum()
        )
        
        # Despesa total (débitos)
        total_expenses = float(
            abs(transactions_df.filter(pl.col("amount") < 0)["amount"].sum())
        )
        
        # Taxa de poupança
        if total_income > 0:
            savings_rate = ((total_income - total_expenses) / total_income) * 100
        else:
            savings_rate = -100.0  # Sem receita = problema sério
        
        # Média mensal de gastos
        months = period_days / 30
        monthly_avg_expenses = total_expenses / months if months > 0 else 0
        
        # Top categorias (se disponível)
        top_categories = []
        if "predicted_category" in transactions_df.columns:
            top_cats = (
                transactions_df
                .filter(pl.col("amount") < 0)
                .group_by("predicted_category")
                .agg(pl.col("amount").sum().alias("total"))
                .sort("total")
                .head(3)
            )
            top_categories = [row["predicted_category"] for row in top_cats.iter_rows(named=True)]
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PERFIL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if savings_rate > 20:
            profile_type = "CONSERVADOR"
        elif savings_rate > 5:
            profile_type = "EQUILIBRADO"
        else:
            profile_type = "GASTADOR"
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TENDÊNCIA (simplificado - análise de últimos 2 meses)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # TODO: Implementar análise de tendência real
        trend = "ESTÁVEL"
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SCORE (0-100)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Base score = savings rate normalizado
        base_score = max(0, min(100, (savings_rate + 20) * 2.5))
        
        # Ajustes
        score = base_score
        
        # Penalidade por gastos muito altos
        if total_expenses > total_income * 0.9:
            score -= 10
        
        # Bônus por poupança consistente
        if savings_rate > 30:
            score += 10
        
        # Normalizar 0-100
        health_score = int(max(0, min(100, score)))
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOGGING
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info(
            f"Financial health calculated: "
            f"score={health_score}, "
            f"profile={profile_type}, "
            f"savings_rate={savings_rate:.1f}%"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RETORNO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return FinancialHealth(
            health_score=health_score,
            profile_type=profile_type,
            savings_rate=round(savings_rate, 2),
            total_income=total_income,
            total_expenses=total_expenses,
            monthly_avg_expenses=monthly_avg_expenses,
            top_categories=top_categories,
            trend=trend
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_risk_level(
        self,
        min_projected_balance: float,
        current_balance: float
    ) -> Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        """
        Determina nível de risco baseado em saldos.
        
        THRESHOLDS:
        - CRITICAL: Saldo vai negativo
        - HIGH: Saldo cai > 80%
        - MEDIUM: Saldo cai 50-80%
        - LOW: Saldo cai < 50%
        """
        if min_projected_balance < 0:
            return "CRITICAL"
        
        drop_pct = (current_balance - min_projected_balance) / current_balance if current_balance > 0 else 0
        
        if drop_pct > 0.8:
            return "HIGH"
        elif drop_pct > 0.5:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_recommendations(
        self,
        risk_level: str,
        safe_to_spend_daily: float,
        total_shadow_invoices: float
    ) -> list[str]:
        """Gera recomendações baseadas em risk level."""
        recommendations = []
        
        if risk_level == "CRITICAL":
            recommendations.append("⚠️ Atenção: Seu saldo pode ficar negativo!")
            recommendations.append("Evite gastos não essenciais nos próximos dias")
        elif risk_level == "HIGH":
            recommendations.append("⚠️ Cuidado: Saldo vai cair muito")
            recommendations.append("Limite gastos ao estritamente necessário")
        elif risk_level == "MEDIUM":
            recommendations.append("⚠️ Atenção moderada ao saldo")
            recommendations.append("Considere adiar compras grandes")
        else:
            recommendations.append("✅ Você está em boa situação financeira")
            recommendations.append(f"Pode gastar até R$ {safe_to_spend_daily:.2f}/dia")
        
        # Recomendação sobre shadow invoices
        if abs(total_shadow_invoices) > 500:
            recommendations.append(
                f"Você tem R$ {abs(total_shadow_invoices):.2f} em "
                "assinaturas/parcelamentos programados"
            )
        
        return recommendations