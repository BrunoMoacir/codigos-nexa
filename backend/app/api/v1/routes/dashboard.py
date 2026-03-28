# app/api/v1/routes/dashboard
from fastapi import APIRouter, HTTPException, status, Depends
from app.core.security import get_current_user

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/summary")
def dashboard_summary(_: str = Depends(get_current_user)):
    """
    Resumo financeiro do dashboard.

    Este endpoint está deprecado — os dados hardcoded foram removidos.
    Use os endpoints abaixo para dados reais do usuário:
      - GET /api/v1/forecast/{user_id}        → previsão completa + saúde financeira
      - GET /api/v1/safe-to-spend/{user_id}   → safe-to-spend + risco
      - GET /api/v1/health-score/{user_id}    → health score histórico
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Este endpoint foi descontinuado. "
            "Use GET /api/v1/forecast/{user_id} para dados financeiros reais."
        ),
    )


@router.get("/safe-to-spend")
def safe_to_spend(_: str = Depends(get_current_user)):
    """
    Quanto o usuário pode gastar com segurança hoje.
    Use GET /api/v1/safe-to-spend/{user_id} para o cálculo completo.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use GET /api/v1/safe-to-spend/{user_id} para obter o safe-to-spend calculado.",
    )
