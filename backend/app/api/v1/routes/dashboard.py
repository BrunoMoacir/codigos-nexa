from fastapi import APIRouter

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/health-score")
def get_health_score():
    """
    Endpoint temporário para validar a estrutura do dashboard.
    Depois será ligado ao ETL + Pluggy.
    """
    return {
        "income": 7200,
        "expenses": 5300,
        "savings_rate": 26.3,
        "health_score": 85
    }
