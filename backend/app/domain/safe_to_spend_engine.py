#app/domain/safe_to_spend_engine
from datetime import date, timedelta


class SafeToSpendEngine:
    """
    Calcula quanto o usuário pode gastar hoje
    sem comprometer suas obrigações futuras.
    """

    def calculate(
        self,
        current_balance: float,
        upcoming_fixed_expenses: float,
        upcoming_subscriptions: float,
        upcoming_installments: float,
        safety_buffer_pct: float = 0.10
    ):
        """
        safety_buffer_pct → margem de segurança (default 10%)
        """

        mandatory_future = (
            upcoming_fixed_expenses +
            upcoming_subscriptions +
            upcoming_installments
        )

        safety_buffer = mandatory_future * safety_buffer_pct

        safe_amount = current_balance - mandatory_future - safety_buffer

        return {
            "current_balance": round(current_balance, 2),
            "mandatory_future": round(mandatory_future, 2),
            "safety_buffer": round(safety_buffer, 2),
            "safe_to_spend": round(max(safe_amount, 0), 2),
            "risk_level": self._risk_level(safe_amount)
        }

    def _risk_level(self, safe_amount: float) -> str:
        if safe_amount <= 0:
            return "CRITICAL"
        elif safe_amount < 300:
            return "HIGH"
        elif safe_amount < 1000:
            return "MEDIUM"
        else:
            return "LOW"
