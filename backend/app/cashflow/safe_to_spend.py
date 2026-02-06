# backend/app/cashflow/safe_to_spend.py
class SafeToSpendCalculator:
    """
    Calcula quanto o usuário pode gastar com segurança.
    """

    def __init__(self, buffer: float = 1000.0):
        self.buffer = buffer

    def calculate(self, cashflow_df, days: int = 30) -> dict:
        min_balance = cashflow_df["projected_balance"].min()

        safe_total = min_balance - self.buffer
        safe_total = max(0.0, safe_total)

        return {
            "days": days,
            "buffer": self.buffer,
            "min_projected_balance": float(min_balance),
            "safe_to_spend_total": safe_total,
            "safe_to_spend_daily": safe_total / days if days else 0.0,
        }
