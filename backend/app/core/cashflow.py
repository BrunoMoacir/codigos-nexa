from typing import List, Dict


def project_cashflow(
    current_balance: float,
    recurring_incomes: List[Dict],
    recurring_expenses: List[Dict],
    months: int = 3,
):
    """
    Projeta fluxo de caixa futuro.
    """

    income = sum(i["amount"] for i in recurring_incomes)
    expenses = sum(abs(e["amount"]) for e in recurring_expenses)

    projections = []

    balance = current_balance

    for month in range(1, months + 1):
        balance += income
        balance -= expenses

        projections.append(
            {
                "month": month,
                "projected_balance": round(balance, 2),
            }
        )

    return projections
