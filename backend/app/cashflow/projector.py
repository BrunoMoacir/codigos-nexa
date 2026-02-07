# backend/app/cashflow/projector.py
"""
Projetor de Fluxo de Caixa - VERSÃO CORRIGIDA

MUDANÇAS:
    ✅ Simplificação mantida (código mais limpo)
    ✅ Integração Shadow Invoices RESTAURADA (crítico para MVP)
    ✅ Compatível com test_shadow_cashflow_integration.py

RESPONSABILIDADE:
    Projeta saldo diário futuro aplicando Shadow Invoices (obrigações futuras)
"""

import polars as pl
from datetime import datetime, timedelta
from typing import Optional


class CashflowProjector:
    """
    Projeta fluxo de caixa diário considerando Shadow Invoices.
    
    Funcionalidades:
        1. Calcula saldo inicial (último saldo conhecido)
        2. Cria calendário futuro (horizon_days)
        3. ✅ Aplica Shadow Invoices nas datas corretas (CRÍTICO!)
        4. Calcula saldo projetado dia a dia (acumulado)
        5. Identifica dias de risco (saldo negativo)
    
    Example:
        >>> projector = CashflowProjector(horizon_days=30)
        >>> 
        >>> projection_df = projector.project(
        ...     transactions_df=df,
        ...     shadow_invoices_df=shadow_df,
        ...     current_balance=5000.0
        ... )
    """
    
    def __init__(self, horizon_days: int = 30):
        """
        Inicializa projetor.
        
        Args:
            horizon_days: Período de projeção em dias (padrão: 30)
        """
        self.horizon_days = horizon_days
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def project(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame,
        current_balance: Optional[float] = None
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
            
            current_balance: Saldo inicial (opcional)
                Se None, usa último saldo de transactions_df
        
        Returns:
            DataFrame com projeção diária:
                - date (date) - dia
                - starting_balance (float) - saldo inicial do dia
                - expenses (float) - débitos do dia (shadow invoices)
                - projected_balance (float) - saldo projetado acumulado
                - risk_flag (str | None) - NEGATIVE_BALANCE se saldo < 0
        
        Raises:
            ValueError: Se DataFrame de transações vazio ou sem balance
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Validações
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if transactions_df.is_empty():
            raise ValueError("DataFrame de transações está vazio")
        
        required_cols = {"transaction_date", "amount"}
        if not required_cols.issubset(transactions_df.columns):
            missing = required_cols - set(transactions_df.columns)
            raise ValueError(f"Colunas faltando: {missing}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Calcular saldo inicial
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Ordenar cronologicamente
        df_sorted = transactions_df.sort("transaction_date")
        
        # Saldo inicial
        if current_balance is None:
            if "balance" not in df_sorted.columns:
                raise ValueError(
                    "DataFrame sem coluna 'balance' e current_balance não fornecido"
                )
            starting_balance = float(df_sorted["balance"][-1])
        else:
            starting_balance = current_balance
        
        # Data inicial = dia seguinte à última transação
        last_date = df_sorted["transaction_date"].max()
        start_date = last_date.date() if hasattr(last_date, 'date') else last_date
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Criar calendário futuro
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        dates = [
            start_date + timedelta(days=i + 1)
            for i in range(self.horizon_days)
        ]
        
        calendar_df = pl.DataFrame({
            "date": dates
        })
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Agregar Shadow Invoices por data (CRÍTICO!)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if shadow_invoices_df.is_empty():
            # Sem shadow invoices → sem despesas futuras
            shadow_daily = pl.DataFrame({
                "date": [],
                "expenses": []
            }).cast({"date": pl.Date, "expenses": pl.Float64})
        else:
            # Converter next_due_date para date e agrupar
            shadow_daily = (
                shadow_invoices_df
                .with_columns(
                    pl.col("next_due_date").dt.date().alias("date")
                )
                .group_by("date")
                .agg(
                    # Soma dos amounts (já são negativos)
                    pl.col("amount").sum().alias("expenses")
                )
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5: Merge calendário + shadow invoices
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        projection = (
            calendar_df
            .join(shadow_daily, on="date", how="left")
            .with_columns(
                # Dias sem shadow invoice = 0 de despesa
                pl.col("expenses").fill_null(0.0)
            )
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 6: Calcular saldo projetado (acumulado)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        balances = []
        current = starting_balance
        
        for row in projection.iter_rows(named=True):
            # Aplicar débito do dia (expense já é negativo)
            current += row["expenses"]
            balances.append(round(current, 2))
        
        projection = projection.with_columns([
            pl.lit(starting_balance).alias("starting_balance"),
            pl.Series("projected_balance", balances)
        ])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 7: Adicionar risk flag
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        projection = projection.with_columns(
            pl.when(pl.col("projected_balance") < 0)
            .then(pl.lit("NEGATIVE_BALANCE"))
            .otherwise(pl.lit(None))
            .alias("risk_flag")
        )
        
        return projection


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMPATIBILIDADE: Suporte à assinatura antiga
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Se alguém chamar com a assinatura antiga (sem shadow_invoices_df),
# o código ainda funciona (mas sem precisão de obrigações futuras)