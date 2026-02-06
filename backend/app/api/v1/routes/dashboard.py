from fastapi import APIRouter
from app.domain.finance_engine import FinanceEngine
from app.domain.safe_to_spend_engine import SafeToSpendEngine

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

finance_engine = FinanceEngine()
safe_engine = SafeToSpendEngine()


@router.get("/summary")
def dashboard_summary():
    income = 7200
    expenses = 5300
    return finance_engine.calculate_summary(income, expenses)


@router.get("/safe-to-spend")
def safe_to_spend():
    """
    Quanto o usuário pode gastar com segurança hoje.
    """

    return safe_engine.calculate(
        current_balance=3800,
        upcoming_fixed_expenses=2100,
        upcoming_subscriptions=180,
        upcoming_installments=620
    )
