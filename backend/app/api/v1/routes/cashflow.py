#app/api/v1/routes/cashflow.py
from fastapi import APIRouter, HTTPException
from app.agent.nexa_financial_agent import NexaFinancialAgent

router = APIRouter(prefix="/cashflow", tags=["Cashflow"])

agent = NexaFinancialAgent()


@router.post("/analyze")
def analyze_cashflow(payload: dict):
    """
    Endpoint financeiro principal do Nexa.
    """

    transactions = payload.get("transactions")

    if not transactions:
        raise HTTPException(400, "Campo 'transactions' é obrigatório")

    result = agent.analyze(transactions)

    return result