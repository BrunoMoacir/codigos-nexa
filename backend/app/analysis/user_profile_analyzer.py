#app/analysis/cashflow_projector
from typing import List, Dict


class UserProfileAnalyzer:
    """
    Analisa o perfil financeiro do usuário com base nas transações.

    Responsável por calcular:
        - Renda mensal
        - Gastos mensais
        - Taxa de poupança
        - Classificação de risco comportamental
    """

    def run(self, transactions: List[Dict]) -> Dict:
        """
        Interface padrão para o Agent.
        """
        return self.analyze(transactions)

    def analyze(self, transactions: List[Dict]) -> Dict:
        """
        Analisa o perfil financeiro.

        Args:
            transactions: lista de transações financeiras

        Returns:
            dict com métricas financeiras principais
        """

        income = sum(t["amount"] for t in transactions if t["amount"] > 0)
        expenses = abs(sum(t["amount"] for t in transactions if t["amount"] < 0))

        savings = income - expenses

        savings_rate = (savings / income) if income > 0 else 0

        if savings_rate >= 0.3:
            risk_profile = "low"
        elif savings_rate >= 0.1:
            risk_profile = "medium"
        else:
            risk_profile = "high"

        return {
            "monthly_income": round(income, 2),
            "monthly_expenses": round(expenses, 2),
            "savings_rate": round(savings_rate, 2),
            "risk_profile": risk_profile
        }
