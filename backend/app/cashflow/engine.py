"""
Cashflow Engine

Orquestra:
- projeção de fluxo
- despesas obrigatórias futuras
- safe-to-spend
- risco financeiro
"""

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator
from app.cashflow.cashflow_projector import CashflowForecastProjector


class CashflowEngine:

    def __init__(self):
        self.projector = CashflowProjector()
        self.safe_to_spend = SafeToSpendCalculator()
        self.forecast = CashflowForecastProjector()

    def analyze(self, df):
        """
        Executa análise completa de cashflow.
        """

        # 1️⃣ Projeção base (saldo atual + despesas futuras)
        base = self.projector.project(df)

        # 2️⃣ Cálculo safe-to-spend
        sts = self.safe_to_spend.calculate(
            current_balance=base.current_balance,
            mandatory_future=base.mandatory_future
        )

        # 3️⃣ Forecast temporal
        forecast = self.forecast.project(
            current_balance=base.current_balance,
            monthly_expenses=base.monthly_avg_expenses
        )

        return {
            "base": base,
            "safe_to_spend": sts,
            "forecast": forecast
        }
