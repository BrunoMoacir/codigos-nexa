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

_agent = None

def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_financial_agent()
    return _agent


@router.post("")
def analyze(transactions: list[dict]):
    """
    Recebe transações e retorna Safe-to-Spend + explicação.
    """

    df = pl.DataFrame(transactions)

    final_state = _get_agent().invoke({
        "transactions": df
    })

    return {
        "safe_to_spend": final_state["safe_to_spend"],
        "explanation": final_state["explanation"]
    }
