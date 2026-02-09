#app/api/v1/routes/dashboard
from fastapi import APIRouter
from app.domain.finance_engine import FinanceEngine
from app.cashflow.safe_to_spend import SafeToSpendCalculator
from app.cashflow.projector import CashflowProjector
from app.etl.shadow_invoices import run_shadow_invoice_detection

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
