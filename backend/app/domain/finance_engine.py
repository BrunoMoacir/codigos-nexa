#app/domain/finance_engine
class FinanceEngine:

    def calculate_summary(self, income: float, expenses: float):
        savings_rate = ((income - expenses) / income) * 100 if income else 0

        health_score = self._calculate_health_score(
            savings_rate=savings_rate,
            expenses=expenses,
            income=income
        )

        return {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "savings_rate": round(savings_rate, 2),
            "health_score": health_score
        }

    def _calculate_health_score(self, savings_rate, expenses, income):
        score = 0

        # Taxa de poupança (50)
        if savings_rate >= 30:
            score += 50
        elif savings_rate >= 20:
            score += 40
        elif savings_rate >= 10:
            score += 30
        elif savings_rate >= 0:
            score += 20

        # Balanço (30)
        if income > expenses:
            score += 30
        elif income == expenses:
            score += 15

        # Proporção gasto/renda (20)
        if income > 0:
            ratio = expenses / income
            if ratio < 0.5:
                score += 20
            elif ratio < 0.7:
                score += 15
            elif ratio < 0.9:
                score += 10

        return min(score, 100)
