# tests/agent/test_agent_router.py
# Testes de router para F11 — Agente Conversacional ReAct com 14 ferramentas

from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.router import router
from app.core.security import get_current_user, require_owner
from app.core.database import get_db

USER = "user_agent_test"


def _mock_db_with_history(messages: list[dict] = None) -> MagicMock:
    db = MagicMock()
    msgs = messages or []
    mock_rows = []
    for i, m in enumerate(msgs):
        row = MagicMock()
        row.id = i + 1
        row.role = m.get("role", "human")
        row.content = m.get("content", "")
        row.created_at = datetime(2026, 1, 1, 12, 0, 0)
        mock_rows.append(row)
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_rows
    db.query.return_value.filter.return_value.delete.return_value = len(msgs)
    return db


def _make_app(auth_user: str = USER, db=None):
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: auth_user
    a.dependency_overrides[require_owner] = lambda user_id: auth_user
    a.dependency_overrides[get_db] = lambda: (db or MagicMock())
    return a


# ── POST /chat/ ───────────────────────────────────────────────────────────────

def test_chat_forbidden_other_user():
    """user_id no body diferente do usuário autenticado → 403."""
    app = _make_app(auth_user="outro_user")
    c = TestClient(app)
    resp = c.post("/chat/", json={"user_id": USER, "message": "Olá"})
    assert resp.status_code == 403


def test_chat_missing_fields_returns_422():
    """Body sem message → 422."""
    app = _make_app()
    c = TestClient(app)
    resp = c.post("/chat/", json={"user_id": USER})
    assert resp.status_code == 422


def test_chat_llm_not_configured_returns_503():
    """Sem API key configurada → 503 SERVICE UNAVAILABLE."""
    app = _make_app()
    c = TestClient(app)
    with patch("app.agent.router.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.OPENAI_API_KEY = "mock"
        resp = c.post("/chat/", json={"user_id": USER, "message": "Qual meu saldo?"})
    assert resp.status_code == 503


def test_chat_success_with_mocked_agent():
    """Com agente mockado retorna 200 e response."""
    mock_result = {"messages": [MagicMock(content="Seu saldo é R$ 1.000.")]}
    mock_db = MagicMock()

    app = _make_app(db=mock_db)
    c = TestClient(app)

    with patch("app.agent.router.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "anthropic"
        mock_settings.ANTHROPIC_API_KEY = "sk-real-key"
        with patch("app.agent.router._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = mock_result
            mock_get_agent.return_value = mock_agent
            resp = c.post("/chat/", json={"user_id": USER, "message": "Qual meu saldo?"})

    assert resp.status_code == 200
    assert "response" in resp.json()
    assert resp.json()["response"] == "Seu saldo é R$ 1.000."


# ── GET /chat/history ─────────────────────────────────────────────────────────

def test_get_history_empty():
    """Histórico vazio → lista vazia."""
    app = _make_app(db=_mock_db_with_history([]))
    c = TestClient(app)
    resp = c.get(f"/chat/history?user_id={USER}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_history_with_messages():
    """Histórico com mensagens → lista com role, content, id."""
    messages = [
        {"role": "human", "content": "Qual meu health score?"},
        {"role": "assistant", "content": "Seu score é 75."},
    ]
    app = _make_app(db=_mock_db_with_history(messages))
    c = TestClient(app)
    resp = c.get(f"/chat/history?user_id={USER}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    roles = {item["role"] for item in data}
    assert "human" in roles
    assert "assistant" in roles
    for item in data:
        assert "id" in item
        assert "content" in item
        assert "created_at" in item


# ── DELETE /chat/history ──────────────────────────────────────────────────────

def test_delete_history_returns_count():
    """DELETE retorna deleted_count."""
    app = _make_app(db=_mock_db_with_history([{"role": "human", "content": "oi"}]))
    c = TestClient(app)
    resp = c.delete(f"/chat/history?user_id={USER}")
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted_count" in data


# ── Inventário de ferramentas (F11 — 14 tools) ───────────────────────────────

def test_all_14_agent_tools_importable():
    """Todas as 14 ferramentas do agente devem ser importáveis e ter método invoke."""
    from app.agent.tools.get_bank_cost_analysis import get_bank_cost_analysis
    from app.agent.tools.get_budget_advice import get_budget_advice
    from app.agent.tools.get_card_optimization import get_card_optimization
    from app.agent.tools.get_financial_forecast import get_financial_forecast
    from app.agent.tools.get_financing_simulation import get_financing_simulation
    from app.agent.tools.get_fiscal_report import get_fiscal_report
    from app.agent.tools.get_goals_summary import get_goals_summary
    from app.agent.tools.get_leverage_simulation import get_leverage_simulation
    from app.agent.tools.get_negotiation_script import get_negotiation_script
    from app.agent.tools.get_peer_comparison import get_peer_comparison
    from app.agent.tools.get_purchase_recommendation import get_purchase_recommendation
    from app.agent.tools.get_spending_alerts import get_spending_alerts
    from app.agent.tools.get_timing_scenarios import get_timing_scenarios
    from app.agent.tools.get_user_profile_context import get_user_profile_context

    tools = [
        get_bank_cost_analysis, get_budget_advice, get_card_optimization,
        get_financial_forecast, get_financing_simulation, get_fiscal_report,
        get_goals_summary, get_leverage_simulation, get_negotiation_script,
        get_peer_comparison, get_purchase_recommendation, get_spending_alerts,
        get_timing_scenarios, get_user_profile_context,
    ]
    assert len(tools) == 14
    for tool in tools:
        assert hasattr(tool, "invoke"), f"Ferramenta {tool} não tem método invoke"
