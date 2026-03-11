import pytest
from app.agent.tools.get_budget_advice import get_budget_advice
from app.agent.tools.get_card_optimization import get_card_optimization
from app.agent.tools.get_financial_forecast import get_financial_forecast
from app.agent.tools.get_financing_simulation import get_financing_simulation
from app.agent.tools.get_fiscal_report import get_fiscal_report
from app.agent.tools.get_goals_summary import get_goals_summary
from app.agent.tools.get_peer_comparison import get_peer_comparison
from app.agent.tools.get_spending_alerts import get_spending_alerts
import json

import os
os.environ["APP_MODE"] = "prod"
os.environ["PLUGGY_CLIENT_ID"] = "dummy"
os.environ["PLUGGY_CLIENT_SECRET"] = "dummy"
# Just to be safe from Settings() validation errors

USER_ID = "golden_user_777"

def test_get_budget_advice_real():
    result = get_budget_advice.invoke({"user_id": USER_ID, "monthly_income": 10000.0})
    assert isinstance(result, str)
    assert len(result) > 50
    assert "Limite sugerido" in result or "Orçamento" in result or "R$" in result

def test_get_card_optimization_real():
    result = get_card_optimization.invoke({
        "user_id": USER_ID,
        "monthly_income": 15000.0,
        "safe_to_spend": 5000.0
    })
    assert isinstance(result, str)
    assert len(result) > 50

def test_get_financial_forecast_real():
    result = get_financial_forecast.invoke({"user_id": USER_ID})
    assert isinstance(result, str)
    assert len(result) > 50
    assert "Burn Rate" in result or "R$" in result

def test_get_financing_simulation_real():
    result = get_financing_simulation.invoke({
        "user_id": USER_ID,
        "monthly_income": 15000.0,
        "target_amount": 500000.0,
        "down_payment": 100000.0
    })
    assert isinstance(result, str)
    assert len(result) > 50

def test_get_fiscal_report_real():
    result = get_fiscal_report.invoke({"user_id": USER_ID})
    assert isinstance(result, str)
    assert len(result) > 50
    # Usually contains something about PJ or Simples Nacional or something
    
def test_get_goals_summary_real():
    result = get_goals_summary.invoke({"user_id": USER_ID})
    assert isinstance(result, str)
    assert len(result) > 50

def test_get_peer_comparison_real():
    result = get_peer_comparison.invoke({"user_id": USER_ID, "monthly_income": 15000.0})
    assert isinstance(result, str)
    assert len(result) > 50

def test_get_spending_alerts_real():
    result = get_spending_alerts.invoke({"user_id": USER_ID})
    assert isinstance(result, str)
    assert len(result) > 50
