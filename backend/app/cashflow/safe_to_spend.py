import polars as pl


class SafeToSpendCalculator:
    """
    Calcula quanto o usuário pode gastar por dia
    sem quebrar o caixa no horizonte analisado.
    """

    def __init__(self, buffer: float = 1000.0):
        self.buffer = buffer

    def calculate(self, cashflow_df: pl.DataFrame, days: int = 30) -> dict:
        if cashflow_df.is_empty():
            raise ValueError("Cashflow vazio")

        min_balance = cashflow_df.select(
            pl.col("projected_balance").min()
        ).item()

        safe_amount = (min_balance - self.buffer) / days

        if safe_amount < 0:
            safe_amount = 0.0

        return {
            "days": days,
            "buffer": self.buffer,
            "min_projected_balance": round(min_balance, 2),
            "safe_to_spend_daily": round(safe_amount, 2),
        }
