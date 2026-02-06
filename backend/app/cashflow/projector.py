# backend/app/cashflow/projector.py
import polars as pl
from datetime import timedelta


class CashflowProjector:
    """
    Projeta fluxo de caixa diário a partir do histórico.
    """

    def __init__(self, horizon_days: int = 30):
        self.horizon_days = horizon_days

    def project(self, df: pl.DataFrame, current_balance: float) -> pl.DataFrame:
        """
        Gera projeção diária de saldo.
        """

        # garante ordenação temporal
        df = df.sort("transaction_date")

        # despesas médias diárias
        debits = df.filter(pl.col("amount") < 0)
        avg_daily_expense = abs(debits["amount"].mean()) if len(debits) > 0 else 0.0

        start_date = df["transaction_date"].max()
        dates = [
            start_date + timedelta(days=i + 1)
            for i in range(self.horizon_days)
        ]

        balances = []
        balance = current_balance

        for _ in range(self.horizon_days):
            balance -= avg_daily_expense
            balances.append(balance)

        return pl.DataFrame({
            "date": dates,
            "starting_balance": [current_balance] * self.horizon_days,
            "expenses": [avg_daily_expense] * self.horizon_days,
            "projected_balance": balances,
        })
