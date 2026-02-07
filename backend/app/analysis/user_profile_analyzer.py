"""
UserProfileAnalyzer

Calcula métricas financeiras globais e gera o perfil do usuário.
"""

class UserProfileAnalyzer:
    """
    Responsável por analisar:
      - renda
      - despesas
      - taxa de poupança
      - health score
      - perfil financeiro
    """

    def analyze(self, income: float, expenses: float) -> dict:
        """
        Analisa o perfil financeiro do usuário.
        """

        savings = income - expenses
        savings_rate = (savings / income * 100) if income > 0 else 0

        health_score = self._calculate_health_score(
            savings_rate=savings_rate,
            expenses=expenses,
            income=income
        )

        profile = self._classify_profile(savings_rate, health_score)

        return {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "savings_rate": round(savings_rate, 2),
            "health_score": health_score,
            "profile": profile
        }

    # ─────────────────────────────────────────────

    def _classify_profile(self, savings_rate: float, score: int) -> str:
        """
        Classifica perfil financeiro.
        """

        if score >= 80:
            return "SAUDÁVEL"
        elif score >= 60:
            return "EQUILIBRADO"
        elif score >= 40:
            return "GASTADOR"
        else:
            return "ALERTA"

    # ─────────────────────────────────────────────

    def _calculate_health_score(
        self,
        savings_rate: float,
        expenses: float,
        income: float
    ) -> int:
        """
        Calcula score de saúde financeira (0-100).
        """

        score = 0

        # FATOR 1 — Taxa de poupança (50 pts)
        if savings_rate >= 30:
            score += 50
        elif savings_rate >= 20:
            score += 40
        elif savings_rate >= 10:
            score += 30
        elif savings_rate >= 0:
            score += 20

        # FATOR 2 — Renda > despesas (30 pts)
        if income > expenses:
            score += 30
        elif income == expenses:
            score += 15

        # FATOR 3 — Proporção gasto/renda (20 pts)
        if income > 0:
            ratio = expenses / income

            if ratio < 0.5:
                score += 20
            elif ratio < 0.7:
                score += 15
            elif ratio < 0.9:
                score += 10

        return min(score, 100)
