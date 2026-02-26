import pytest
from app.agent.tools.get_card_optimization import get_card_optimization

def test_get_card_optimization_tool_missing_params():
    # LLM might call without income or safe_to_spend
    result = get_card_optimization.invoke({"user_id": "test_user"})
    assert "Preciso saber sua renda mensal" in result

def test_get_card_optimization_tool_success(monkeypatch):
    monkeypatch.setattr("app.optimizer.services.optimizer_service.save_optimization_report", lambda r: None)
    
    # Provide safe to spend, should return a report output
    result = get_card_optimization.invoke({
        "user_id": "test_user",
        "monthly_income": 3000.0,
        "safe_to_spend": 1000.0
    })
    
    assert "Relatório de Otimização" in result
    assert "Recomendação Principal" in result
    assert "Estratégia" in result
