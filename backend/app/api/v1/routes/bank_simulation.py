from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user

router = APIRouter(
    prefix="/banks",
    tags=["Bank Simulation"]
)

# Importação lazy para não quebrar startup em produção (tests/ não instalado)
try:
    from tests.fixtures.mocks.factory import simulate_bank as _simulate_bank
    _SIMULATION_AVAILABLE = True
except ImportError:
    _simulate_bank = None
    _SIMULATION_AVAILABLE = False


@router.get("/simulate/{bank}")
def simulate_bank_endpoint(bank: str, _: str = Depends(get_current_user)):
    if not _SIMULATION_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Simulação de banco não disponível neste ambiente.",
        )
    try:
        transactions = _simulate_bank(bank)
        return {"bank": bank, "transactions": transactions}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
