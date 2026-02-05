import polars as pl
from app.agent.graph import build_financial_agent

def test_financial_agent_happy_path():
    df = pl.DataFrame({
        "date": ["2026-01-01", "2026-01-10"],
        "amount": [-100, -100],
        "description": ["NETFLIX", "NETFLIX"]
    })

    agent = build_financial_agent()

    final_state = agent.invoke({
        "transactions": df
    })

    assert "safe_to_spend" in final_state
    assert "explanation" in final_state
    assert final_state["safe_to_spend"]["safe_to_spend_daily"] >= 0
