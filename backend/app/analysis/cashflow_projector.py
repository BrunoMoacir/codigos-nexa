from app.core.cashflow import project_cashflow


class CashflowProjector:

    def run(
        self,
        current_balance,
        recurring_incomes,
        recurring_expenses,
        months=3,
    ):
        return project_cashflow(
            current_balance,
            recurring_incomes,
            recurring_expenses,
            months,
        )
