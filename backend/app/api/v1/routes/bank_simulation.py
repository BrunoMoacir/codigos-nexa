from fastapi import APIRouter, HTTPException
from app.simulations.factory import simulate_bank

router = APIRouter(
    prefix="/banks",
    tags=["Bank Simulation"]
)


@router.get("/simulate/{bank}")
def simulate_bank_endpoint(bank: str):
    try:
        transactions = simulate_bank(bank)
        return {
            "bank": bank,
            "transactions": transactions
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
