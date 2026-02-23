#app/api/v1/routes/dashboard
from fastapi import APIRouter, HTTPException, status
from app.domain.finance_engine import FinanceEngine

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

finance_engine = FinanceEngine()


@router.get("/summary")
def dashboard_summary():
    income = 7200
    expenses = 5300
    return finance_engine.calculate_summary(income, expenses)


@router.get("/safe-to-spend")
def safe_to_spend():
    """
    Quanto o usuário pode gastar com segurança hoje.
    Use GET /api/v1/forecast/{user_id} para o cálculo completo.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use GET /api/v1/forecast/{user_id} para obter o safe-to-spend calculado.",
    )
