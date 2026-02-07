"""
app/cashflow/projector.py - Projetor de Fluxo de Caixa DEFINITIVO

RESPONSABILIDADE:
    Projeta saldo diário futuro aplicando Shadow Invoices (obrigações futuras)

INTEGRAÇÃO:
    - Usa Shadow Invoices (assinaturas + parcelamentos futuros)
    - Calcula saldo projetado dia a dia
    - Identifica dias de risco (saldo negativo)

USAGE:
    projector = CashflowProjector(horizon_days=30)
    projection_df = projector.project(
        transactions_df=df,
        shadow_invoices_df=shadow_df
    )
"""

import logging
import polars as pl
from datetime import datetime, timedelta, date
from dataclasses import dataclass
from typing import Optional, Literal

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class ProjectionSummary:
    """
    Resumo da projeção de cashflow.
    
    Attributes:
        horizon_days: Período projetado (dias)
        starting_balance: Saldo inicial
        ending_balance: Saldo final projetado
        worst_balance: Menor saldo atingido
        negative_day: Primeiro dia com saldo negativo (None se nunca)
        risk_level: LOW/MEDIUM/HIGH/CRITICAL
        total_shadow_impact: Impacto total das shadow invoices
    """
    
    horizon_days: int
    starting_balance: float
    ending_balance: float
    worst_balance: float
    negative_day: Optional[int]
    risk_level: RiskLevel
    total_shadow_impact: float
    
    def to_dict(self) -> dict:
        """Converte para dict (útil para JSON)."""
        return {
            "horizon_days": self.horizon_days,
            "starting_balance": self.starting_balance,
            "ending_balance": self.ending_balance,
            "worst_balance": self.worst_balance,
            "negative_day": self.negative_day,
            "risk_level": self.risk_level,
            "total_shadow_impact": self.total_shadow_impact
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASHFLOW PROJECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CashflowProjector:
    """
    Projeta saldo diário futuro considerando Shadow Invoices.
    
    Funcionalidades:
        1. Calcula saldo inicial (último saldo conhecido)
        2. Cria calendário futuro (horizon_days)
        3. Aplica Shadow Invoices nas datas corretas
        4. Calcula saldo projetado dia a dia (acumulado)
        5. Identifica dias de risco (saldo negativo)
        6. Calcula métricas de resumo
    
    Example:
        >>> projector = CashflowProjector(horizon_days=30)
        >>> 
        >>> projection_df = projector.project(
        ...     transactions_df=df,
        ...     shadow_invoices_df=shadow_df
        ... )
        >>> 
        >>> print(projection_df.head())
        ┌────────────┬───────────────────┬───────────────────┬───────────┐
        │ date       ┆ shadow_amount     ┆ projected_balance ┆ risk_flag │
        ├────────────┼───────────────────┼───────────────────┼───────────┤
        │ 2026-02-07 ┆ -49.90            ┆ 5000.10           ┆ null      │
        │ 2026-02-08 ┆ 0.0               ┆ 5000.10           ┆ null      │
        │ 2026-02-09 ┆ -21.90            ┆ 4978.20           ┆ null      │
        └────────────┴───────────────────┴───────────────────┴───────────┘
    """
    
    def __init__(self, horizon_days: int = 30):
        """
        Inicializa projetor.
        
        Args:
            horizon_days: Período de projeção em dias (padrão: 30)
        """
        self.horizon_days = horizon_days
        self.logger = logging.getLogger(__name__)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def project(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Projeta saldo diário futuro.
        
        Args:
            transactions_df: DataFrame normalizado com transações
                Colunas obrigatórias:
                - transaction_date (datetime)
                - amount (float)
                - balance (float) - saldo após a transação
            
            shadow_invoices_df: DataFrame com obrigações futuras
                Colunas obrigatórias:
                - amount (float) - valor da obrigação (negativo)
                - next_due_date (datetime) - data de vencimento
        
        Returns:
            DataFrame com projeção diária:
                - date (date) - dia
                - shadow_amount (float) - débitos do dia (shadow invoices)
                - projected_balance (float) - saldo projetado acumulado
                - risk_flag (str | None) - NEGATIVE_BALANCE se saldo < 0
        
        Raises:
            ValueError: Se DataFrame de transações vazio ou sem balance
        
        Example:
            >>> df_projection = projector.project(df, shadow_df)
            >>> 
            >>> # Ver dias de risco
            >>> risky_days = df_projection.filter(
            ...     pl.col("risk_flag") == "NEGATIVE_BALANCE"
            ... )
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Validações
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("DataFrame de transações está vazio")
        
        required_txn_cols = {"transaction_date", "amount", "balance"}
        if not required_txn_cols.issubset(transactions_df.columns):
            missing = required_txn_cols - set(transactions_df.columns)
            raise ValueError(f"Colunas faltando em transactions_df: {missing}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Calcular saldo inicial
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Saldo inicial = último saldo conhecido
        last_tx = transactions_df.sort("transaction_date").tail(1)
        starting_balance = float(last_tx["balance"][0])
        start_date = last_tx["transaction_date"][0].date()
        
        self.logger.info(
            f"Saldo inicial: R$ {starting_balance:,.2f} (data: {start_date})"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Criar calendário futuro
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        dates = [
            start_date + timedelta(days=i)
            for i in range(1, self.horizon_days + 1)
        ]
        
        calendar_df = pl.DataFrame({
            "date": dates
        })
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Agregar Shadow Invoices por data
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if shadow_invoices_df.is_empty():
            self.logger.warning("Nenhuma shadow invoice detectada")
            shadow_daily = pl.DataFrame({
                "date": [],
                "shadow_amount": []
            }).cast({"date": pl.Date, "shadow_amount": pl.Float64})
        else:
            # Converter next_due_date para date e agrupar
            shadow_daily = (
                shadow_invoices_df
                .with_columns(
                    pl.col("next_due_date").dt.date().alias("date")
                )
                .group_by("date")
                .agg(
                    pl.col("amount").sum().alias("shadow_amount")
                )
            )
            
            self.logger.debug(
                f"Shadow invoices agregadas em {shadow_daily.height} dias"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5: Merge calendário + shadow invoices
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        projection = (
            calendar_df
            .join(shadow_daily, on="date", how="left")
            .with_columns(
                pl.col("shadow_amount").fill_null(0.0)
            )
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 6: Calcular saldo projetado (acumulado)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        balances = []
        current_balance = starting_balance
        
        for row in projection.iter_rows(named=True):
            # Aplicar débito do dia (shadow invoice)
            current_balance += row["shadow_amount"]  # amount já é negativo
            balances.append(round(current_balance, 2))
        
        projection = projection.with_columns(
            pl.Series("projected_balance", balances)
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 7: Adicionar risk flag
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        projection = projection.with_columns(
            pl.when(pl.col("projected_balance") < 0)
            .then(pl.lit("NEGATIVE_BALANCE"))
            .otherwise(pl.lit(None))
            .alias("risk_flag")
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOG RESUMO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        ending_balance = balances[-1]
        risky_days = projection.filter(pl.col("risk_flag").is_not_null()).height
        
        self.logger.info(
            f"Projeção concluída: "
            f"Saldo inicial: R$ {starting_balance:,.2f}, "
            f"Saldo final: R$ {ending_balance:,.2f}, "
            f"Dias de risco: {risky_days}"
        )
        
        return projection
    
    def get_summary(
        self,
        projection_df: pl.DataFrame,
        starting_balance: float
    ) -> ProjectionSummary:
        """
        Calcula resumo da projeção.
        
        Args:
            projection_df: DataFrame retornado por project()
            starting_balance: Saldo inicial usado na projeção
        
        Returns:
            ProjectionSummary com métricas agregadas
        
        Example:
            >>> summary = projector.get_summary(projection_df, 5000.0)
            >>> print(summary.risk_level)
            'LOW'
            >>> print(summary.negative_day)
            None
        """
        # Calcular métricas
        ending_balance = float(projection_df["projected_balance"][-1])
        worst_balance = float(projection_df["projected_balance"].min())
        total_shadow_impact = float(projection_df["shadow_amount"].sum())
        
        # Primeiro dia com saldo negativo
        negative_days = projection_df.filter(
            pl.col("risk_flag") == "NEGATIVE_BALANCE"
        )
        
        if negative_days.is_empty():
            negative_day = None
        else:
            # Calcular dia (1-based index)
            first_negative_date = negative_days["date"][0]
            start_date = projection_df["date"][0]
            negative_day = (first_negative_date - start_date).days + 1
        
        # Calcular risk level
        risk_level = self._classify_risk(negative_day, worst_balance)
        
        return ProjectionSummary(
            horizon_days=self.horizon_days,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            worst_balance=worst_balance,
            negative_day=negative_day,
            risk_level=risk_level,
            total_shadow_impact=total_shadow_impact
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _classify_risk(
        self,
        negative_day: Optional[int],
        worst_balance: float
    ) -> RiskLevel:
        """
        Classifica risco financeiro.
        
        Critérios:
            CRITICAL: Saldo já negativo ou fica negativo em ≤3 dias
            HIGH: Saldo fica negativo em 4-7 dias
            MEDIUM: Saldo fica negativo em 8-30 dias
            LOW: Saldo nunca fica negativo
        
        Args:
            negative_day: Dia do primeiro saldo negativo (None se nunca)
            worst_balance: Menor saldo atingido
        
        Returns:
            RiskLevel
        """
        # Se nunca fica negativo
        if negative_day is None:
            # Mas se o pior saldo for muito baixo, ainda é médio risco
            if worst_balance < 500:
                return "MEDIUM"
            return "LOW"
        
        # Saldo fica negativo
        if negative_day <= 3:
            return "CRITICAL"
        elif negative_day <= 7:
            return "HIGH"
        else:
            return "MEDIUM"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (Convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def project_cashflow(
    transactions_df: pl.DataFrame,
    shadow_invoices_df: pl.DataFrame,
    horizon_days: int = 30
) -> tuple[pl.DataFrame, ProjectionSummary]:
    """
    Função helper que encapsula CashflowProjector.
    
    Útil para imports diretos:
        from app.cashflow.projector import project_cashflow
    
    Args:
        transactions_df: DataFrame com transações
        shadow_invoices_df: DataFrame com shadow invoices
        horizon_days: Período de projeção
    
    Returns:
        (projection_df, summary)
    
    Example:
        >>> projection_df, summary = project_cashflow(df, shadow_df, 30)
        >>> print(summary.risk_level)
        'LOW'
    """
    projector = CashflowProjector(horizon_days=horizon_days)
    
    # Projetar
    projection_df = projector.project(transactions_df, shadow_invoices_df)
    
    # Calcular resumo
    starting_balance = float(
        transactions_df.sort("transaction_date").tail(1)["balance"][0]
    )
    summary = projector.get_summary(projection_df, starting_balance)
    
    return projection_df, summary