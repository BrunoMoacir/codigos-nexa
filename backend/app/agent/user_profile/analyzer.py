"""
User Profile Analyzer

Constrói o perfil financeiro do usuário:
- renda
- despesas
- poupança
- score de saúde financeira
"""

class UserProfileAnalyzer:
    """
    Analisa dados financeiros e gera métricas de saúde financeira.
    """

    def analyze(
        self,
        income: float,
        expenses: float
    ) -> dict:
        """
        Gera o perfil financeiro do usuário.

        Args:
            income: total de receitas
            expenses: total de despesas

        Returns:
            dict com métricas financeiras
        """
        savings = income - expenses
        savings_rate = (savings / income * 100) if income > 0 else 0

        health_score = self._calculate_health_score(
            savings_rate=savings_rate,
            expenses=expenses,
            income=income
        )

        return {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "savings": round(savings, 2),
            "savings_rate": round(savings_rate, 2),
            "health_score": health_score
        }

    def _calculate_health_score(
        self,
        savings_rate: float,
        expenses: float,
        income: float
    ) -> int:
        """
        Calcula score financeiro (0-100).

        Métrica composta:
        - taxa de poupança
        - balanço positivo
        - proporção gasto/renda
        """
        score = 0

        # Fator 1: taxa de poupança
        if savings_rate >= 30:
            score += 50
        elif savings_rate >= 20:
            score += 40
        elif savings_rate >= 10:
            score += 30
        elif savings_rate >= 0:
            score += 20

        # Fator 2: renda > despesas
        if income > expenses:
            score += 30
        elif income == expenses:
            score += 15

        # Fator 3: proporção gasto/renda
        if income > 0:
            ratio = expenses / income
            if ratio < 0.5:
                score += 20
            elif ratio < 0.7:
                score += 15
            elif ratio < 0.9:
                score += 10

        return min(score, 100)
