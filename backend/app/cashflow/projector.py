# app/cashflow/projector.py

from datetime import timedelta
import polars as pl


class CashflowProjector:
    def __init__(self, horizon_days: int = 90):
        self.horizon_days = horizon_days

    def project(
        self,
        core_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Projeta o saldo futuro dia a dia usando:
        - último balance conhecido
        - shadow invoices (obrigações futuras)
        """

        # Ordenação defensiva
        core_df = core_df.sort("transaction_date")

        last_balance = core_df.select("balance").tail(1).item()
        last_date = core_df.select("transaction_date").tail(1).item()

        # Gera range diário
        future_dates = [
            last_date + timedelta(days=i)
            for i in range(1, self.horizon_days + 1)
        ]

        projection = pl.DataFrame({
            "date": future_dates,
            "starting_balance": [last_balance] * self.horizon_days,
            "expenses": [0.0] * self.horizon_days,
            "projected_balance": [last_balance] * self.horizon_days
        })

        # Aplica shadow invoices
        if shadow_invoices_df is not None and len(shadow_invoices_df) > 0:
            for row in shadow_invoices_df.iter_rows(named=True):
                due_date = row["next_due_date"].date()
                amount = row["amount"]

                projection = projection.with_columns(
                    pl.when(pl.col("date").dt.date() == due_date)
                    .then(pl.col("expenses") + amount)
                    .otherwise(pl.col("expenses"))
                    .alias("expenses")
                )

        # Recalcula saldo acumulado
        balances = []
        current_balance = last_balance

        for exp in projection["expenses"]:
            current_balance += exp
            balances.append(current_balance)

        projection = projection.with_columns(
            pl.Series("projected_balance", balances)
        )

        return projection
