# app/etl/cashflow/cashflow_projector.py
import polars as pl
from datetime import datetime, timedelta, timezone


class CashflowProjector:
    """
    Projeta saldo diário futuro aplicando Shadow Invoices.

    Responsabilidade única:
    - Dado um saldo inicial
    - + entradas conhecidas
    - - despesas conhecidas
    - - shadow invoices futuras
    """

    def __init__(self, horizon_days: int = 90):
        self.horizon_days = horizon_days

    def project(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        Args:
            transactions_df: DataFrame normalizado
                Obrigatório conter:
                - transaction_date (datetime)
                - amount (float)
                - balance (float)  # saldo após a transação
            shadow_invoices_df:
                - amount (float)
                - next_due_date (datetime)

        Returns:
            DataFrame:
                date | projected_balance | risk_flag
        """

        # 🔹 1. Saldo inicial = último saldo conhecido
        last_tx = (
            transactions_df
            .sort("transaction_date")
            .tail(1)
        )

        if last_tx.is_empty():
            raise ValueError("Não é possível projetar sem transações.")

        starting_balance = last_tx["balance"][0]
        start_date = last_tx["transaction_date"][0].date()

        # 🔹 2. Criar calendário futuro
        dates = [
            start_date + timedelta(days=i)
            for i in range(1, self.horizon_days + 1)
        ]

        calendar_df = pl.DataFrame({
            "date": dates
        })

        # 🔹 3. Agregar shadow invoices por data
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

        # 🔹 4. Merge calendário + shadow invoices
        projection = (
            calendar_df
            .join(shadow_daily, on="date", how="left")
            .with_columns(
                pl.col("shadow_amount").fill_null(0.0)
            )
        )

        # 🔹 5. Calcular saldo projetado acumulado
        balances = []
        current_balance = starting_balance

        for row in projection.iter_rows(named=True):
            current_balance += row["shadow_amount"]
            balances.append(current_balance)

        projection = projection.with_columns(
            pl.Series("projected_balance", balances)
        )

        # 🔹 6. Risk flag
        projection = projection.with_columns(
            pl.when(pl.col("projected_balance") < 0)
            .then(pl.lit("NEGATIVE_BALANCE"))
            .otherwise(pl.lit(None))
            .alias("risk_flag")
        )

        return projection
