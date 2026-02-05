"""
app/api/v1/routes/analyze.py
Endpoint principal de análise financeira (Safe-to-Spend)
"""

from fastapi import APIRouter
import polars as pl

from app.agent.graph import build_financial_agent

router = APIRouter(
    prefix="/analyze",
    tags=["Financial Analysis"]
)

agent = build_financial_agent()


@router.post("")
def analyze(transactions: list[dict]):
    """
    Recebe transações e retorna Safe-to-Spend + explicação.
    """

    df = pl.DataFrame(transactions)

    final_state = agent.invoke({
        "transactions": df
    })

    return {
        "safe_to_spend": final_state["safe_to_spend"],
        "explanation": final_state["explanation"]
    }
