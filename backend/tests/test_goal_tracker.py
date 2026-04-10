# tests/test_goal_tracker.py
# Testes para MX.2 — Sistema de Metas Financeiras

import math
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app.goals.tracker import GoalTracker, Goal, GoalProjection, _months_until, _add_months


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _future_date(months: int = 24) -> str:
    """Retorna uma data futura como string 'YYYY-MM-DD'."""
    d = _add_months(date.today(), months)
    return d.isoformat()


def _make_goal(
    current: float = 0.0,
    target: float = 50_000.0,
    months_ahead: int = 24,
    monthly_actual: float = 0.0,
    status: str = "ACTIVE",
) -> Goal:
    from datetime import datetime
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    target_date = _future_date(months_ahead)
    monthly_needed = round((target - current) / months_ahead, 2) if months_ahead > 0 else None
    return Goal(
        goal_id="test-goal-id",
        user_id="u1",
        name="Entrada do Apartamento",
        goal_type="imovel",
        target_amount=target,
        current_amount=current,
        target_date=target_date,
        monthly_contribution_needed=monthly_needed,
        monthly_contribution_actual=monthly_actual if monthly_actual > 0 else None,
        status=status,
        created_at=now_str,
        updated_at=now_str,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES UTILITÁRIOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_months_until_future():
    future = _add_months(date.today(), 6)
    assert _months_until(future) >= 5


def test_months_until_past():
    past = date.today() - timedelta(days=30)
    assert _months_until(past) == 0


def test_add_months_normal():
    d = date(2026, 1, 15)
    assert _add_months(d, 3) == date(2026, 4, 15)


def test_add_months_crosses_year():
    d = date(2025, 11, 10)
    assert _add_months(d, 3) == date(2026, 2, 10)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES DO GOAL MODEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_goal_progress_pct():
    goal = _make_goal(current=10_000.0, target=40_000.0)
    assert goal.progress_pct == pytest.approx(25.0, abs=0.1)


def test_goal_remaining():
    goal = _make_goal(current=10_000.0, target=50_000.0)
    assert goal.remaining == pytest.approx(40_000.0, abs=0.1)


def test_goal_progress_pct_complete():
    goal = _make_goal(current=50_000.0, target=50_000.0)
    assert goal.progress_pct == pytest.approx(100.0, abs=0.1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES DO GoalTracker (sem banco — mock do DuckDB)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_calc_monthly_needed_with_date():
    """Com data alvo, deve calcular corretamente."""
    tracker = GoalTracker()
    result = tracker._calc_monthly_needed(
        current=0.0,
        target=24_000.0,
        target_date=_future_date(24),
    )
    # 24_000 / ~24 meses ≈ R$1.000/mês
    assert result is not None
    assert 800.0 <= result <= 1200.0  # tolerância para meses parciais


def test_calc_monthly_needed_without_date():
    """Sem data alvo, deve retornar None."""
    tracker = GoalTracker()
    result = tracker._calc_monthly_needed(0.0, 50_000.0, None)
    assert result is None


def test_calc_monthly_needed_already_achieved():
    """Meta já atingida → 0."""
    tracker = GoalTracker()
    result = tracker._calc_monthly_needed(50_000.0, 50_000.0, _future_date(12))
    assert result == 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES DE PROJEÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_projection_on_track():
    """Contribuição igual ao necessário → on_track=True."""
    monthly = 2_000.0
    goal = _make_goal(current=0.0, target=48_000.0, months_ahead=24, monthly_actual=monthly)
    goal.monthly_contribution_actual = monthly

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)

    assert proj.on_track is True
    assert proj.gap == pytest.approx(0.0, abs=50.0)


def test_projection_off_track():
    """Contribuição menor que o necessário → on_track=False e gap > 0."""
    goal = _make_goal(current=0.0, target=50_000.0, months_ahead=12, monthly_actual=500.0)
    goal.monthly_contribution_actual = 500.0  # necessita ~4166/mês

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)

    assert proj.on_track is False
    assert proj.gap > 0


def test_projection_no_contribution():
    """Sem contribuição → gap = monthly_needed, projected_date = None."""
    goal = _make_goal(current=0.0, target=30_000.0, months_ahead=24, monthly_actual=0.0)

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)

    assert proj.projected_completion_date is None
    assert proj.gap == pytest.approx(proj.monthly_needed, abs=1.0)
    assert "Nenhuma contribuição" in proj.suggestion


def test_projection_suggestion_completed():
    """Meta já concluída → suggestion de parabéns."""
    goal = _make_goal(current=50_000.0, target=50_000.0, status="COMPLETED")

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)
    assert "concluída" in proj.suggestion.lower() or "Parabéns" in proj.suggestion


def test_projection_suggestion_with_gap():
    """Com gap, suggestion deve mencionar o valor a aumentar."""
    goal = _make_goal(current=0.0, target=24_000.0, months_ahead=12, monthly_actual=500.0)
    goal.monthly_contribution_actual = 500.0

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)

    assert proj.gap > 0
    assert "Faltam" in proj.suggestion or "R$" in proj.suggestion


def test_projection_recalculates_when_stored_value_is_zero():
    """Se monthly_contribution_needed estiver zerado, a projeção deve recalcular com base na meta."""
    goal = _make_goal(current=8_000.0, target=30_000.0, months_ahead=6)
    goal.monthly_contribution_needed = 0.0

    tracker = GoalTracker()
    proj = tracker.get_projection(goal)

    assert proj.monthly_needed > 0
    payload = proj.to_dict()
    assert payload["monthly_contribution_needed"] == pytest.approx(proj.monthly_needed, abs=0.01)
    assert payload["months_to_complete"] == payload["months_remaining"]


def test_update_progress_completes_goal():
    """Adicionar o valor restante completo deve marcar meta como COMPLETED."""
    goal = _make_goal(current=45_000.0, target=50_000.0, months_ahead=6)

    # Mockar _load e _update para não precisar de DuckDB real
    tracker = GoalTracker()
    tracker._load = lambda gid: goal
    updated_goals = []
    tracker._update = lambda g: updated_goals.append(g)

    result = tracker.update_progress("test-goal-id", amount_to_add=5_000.0)
    assert result.status == "COMPLETED"
    assert result.current_amount == pytest.approx(50_000.0, abs=1.0)


def test_update_progress_partial():
    """Progresso parcial não deve marcar como COMPLETED."""
    goal = _make_goal(current=10_000.0, target=50_000.0, months_ahead=24)

    tracker = GoalTracker()
    tracker._load = lambda gid: goal
    tracker._update = lambda g: None

    result = tracker.update_progress("test-goal-id", amount_to_add=5_000.0)
    assert result.status == "ACTIVE"
    assert result.current_amount == pytest.approx(15_000.0, abs=1.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE API ENDPOINT (sem banco)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.goals.router import router as goals_router
from app.core.security import get_current_user

_app = FastAPI()
_app.include_router(goals_router)
_app.dependency_overrides[get_current_user] = lambda: "u1"
_client = TestClient(_app)


def test_api_create_goal_validation_past_date():
    """Data passada deve retornar 422."""
    response = _client.post("/goals/u1", json={
        "name": "Viagem",
        "target_amount": 10000.0,
        "target_date": "2020-01-01",
    })
    assert response.status_code == 422


def test_api_create_goal_negative_amount():
    """Valor negativo deve retornar 422."""
    response = _client.post("/goals/u1", json={
        "name": "Meta",
        "target_amount": -500.0,
    })
    assert response.status_code == 422


def test_api_create_goal_success(monkeypatch):
    """POST com dados válidos deve retornar 201 e o goal criado."""
    from datetime import datetime
    from app.goals.tracker import Goal

    fake_goal = Goal(
        goal_id="fake-id",
        user_id="u1",
        name="Viagem para Europa",
        goal_type="viagem",
        target_amount=15_000.0,
        current_amount=0.0,
        target_date=_future_date(18),
        monthly_contribution_needed=833.0,
        monthly_contribution_actual=None,
        status="ACTIVE",
        created_at="2026-03-03T00:00:00Z",
        updated_at="2026-03-03T00:00:00Z",
    )

    monkeypatch.setattr(
        "app.goals.tracker.GoalTracker",
        lambda: MagicMock(create_goal=lambda **kw: fake_goal)
    )

    response = _client.post("/goals/u1", json={
        "name": "Viagem para Europa",
        "goal_type": "viagem",
        "target_amount": 15_000.0,
        "target_date": _future_date(18),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["goal_id"] == "fake-id"
    assert data["status"] == "ACTIVE"


def test_api_get_goal_not_found(monkeypatch):
    """GET de goal inexistente deve retornar 404."""
    tracker_mock = MagicMock()
    tracker_mock._load.side_effect = LookupError("not found")
    monkeypatch.setattr(
        "app.goals.tracker.GoalTracker",
        lambda: tracker_mock,
    )
    response = _client.get("/goals/u1/nonexistent-id")
    assert response.status_code == 404
