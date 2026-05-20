# tests/test_goals_router.py
# Testes de router HTTP para MX.2 — Metas Financeiras (CRUD + projeção)

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.goals.router import router
from app.core.security import get_current_user
from app.core.database import get_db


USER = "user_goals_test"
GOAL_ID = "goal-abc-123"


def _make_app(auth_user: str = USER):
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: auth_user
    a.dependency_overrides[get_db] = lambda: MagicMock()
    return a


app = _make_app()
client = TestClient(app)


def _future_date(days: int = 365) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _mock_goal(goal_id: str = GOAL_ID, user_id: str = USER, status: str = "ACTIVE") -> MagicMock:
    g = MagicMock()
    g.goal_id = goal_id
    g.user_id = user_id
    g.name = "Viagem"
    g.goal_type = "viagem"
    g.target_amount = 10000.0
    g.current_amount = 2000.0
    g.status = status
    g.to_dict.return_value = {
        "goal_id": goal_id, "user_id": user_id, "name": "Viagem",
        "goal_type": "viagem", "target_amount": 10000.0, "current_amount": 2000.0,
        "status": status,
    }
    return g


def _mock_projection() -> MagicMock:
    p = MagicMock()
    p.to_dict.return_value = {"months_to_complete": 8, "on_track": True}
    return p


# ── POST /goals/{user_id} ─────────────────────────────────────────────────────

def test_create_goal_missing_required_fields():
    """Sem target_amount → 422."""
    resp = client.post(f"/goals/{USER}", json={"name": "Meta"})
    assert resp.status_code == 422


def test_create_goal_negative_amount():
    """target_amount negativo → 422."""
    resp = client.post(f"/goals/{USER}", json={"name": "Meta", "target_amount": -100})
    assert resp.status_code == 422


def test_create_goal_past_date():
    """target_date no passado → 422."""
    resp = client.post(f"/goals/{USER}", json={
        "name": "Meta", "target_amount": 5000.0, "target_date": "2020-01-01"
    })
    assert resp.status_code == 422


def test_create_goal_forbidden_other_user():
    """Tentar criar meta para outro usuário → 403."""
    other_app = _make_app(auth_user="outro_user")
    other_client = TestClient(other_app)
    with patch("app.goals.router._build_goal_tracker"):
        resp = other_client.post(f"/goals/{USER}", json={"name": "Meta", "target_amount": 5000.0})
    assert resp.status_code == 403


def test_create_goal_success():
    """POST válido → 201 com dados da meta."""
    goal = _mock_goal()
    tracker = MagicMock()
    tracker.create_goal.return_value = goal

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        with patch("app.goals.router.invalidate_user_cache"):
            resp = client.post(f"/goals/{USER}", json={
                "name": "Viagem", "goal_type": "viagem",
                "target_amount": 10000.0, "target_date": _future_date(),
            })
    assert resp.status_code == 201
    assert resp.json()["goal_id"] == GOAL_ID


# ── GET /goals/{user_id} ──────────────────────────────────────────────────────

def test_list_goals_returns_structure():
    """GET lista → retorna user_id, goals e total."""
    goal = _mock_goal()
    tracker = MagicMock()
    tracker.list_goals.return_value = [goal]
    tracker.get_projection.return_value = _mock_projection()

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        with patch("app.goals.router.get_transactions_for_user", return_value=MagicMock(is_empty=lambda: True)):
            resp = client.get(f"/goals/{USER}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == USER
    assert data["total"] == 1
    assert len(data["goals"]) == 1


def test_list_goals_no_projections():
    """include_projections=false → goals sem campo projection."""
    goal = _mock_goal()
    tracker = MagicMock()
    tracker.list_goals.return_value = [goal]

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        with patch("app.goals.router.get_transactions_for_user", return_value=MagicMock(is_empty=lambda: True)):
            resp = client.get(f"/goals/{USER}?include_projections=false")
    assert resp.status_code == 200
    assert "projection" not in resp.json()["goals"][0]


# ── GET /goals/{user_id}/{goal_id} ────────────────────────────────────────────

def test_get_goal_not_found():
    """Goal inexistente → 404."""
    tracker = MagicMock()
    tracker._load.side_effect = LookupError("not found")

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        resp = client.get(f"/goals/{USER}/{GOAL_ID}")
    assert resp.status_code == 404


def test_get_goal_success():
    """Goal existente → 200 com projection."""
    goal = _mock_goal()
    tracker = MagicMock()
    tracker._load.return_value = goal
    tracker.get_projection.return_value = _mock_projection()

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        resp = client.get(f"/goals/{USER}/{GOAL_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal_id"] == GOAL_ID
    assert "projection" in data


# ── PATCH /goals/{user_id}/{goal_id}/progress ─────────────────────────────────

def test_update_progress_invalid_amount():
    """amount_to_add <= 0 → 422."""
    resp = client.patch(
        f"/goals/{USER}/{GOAL_ID}/progress",
        json={"amount_to_add": 0},
    )
    assert resp.status_code == 422


def test_update_progress_goal_not_active():
    """Meta COMPLETED → 422."""
    goal = _mock_goal(status="COMPLETED")
    tracker = MagicMock()
    tracker._load.return_value = goal

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        resp = client.patch(
            f"/goals/{USER}/{GOAL_ID}/progress",
            json={"amount_to_add": 500.0},
        )
    assert resp.status_code == 422


def test_update_progress_success():
    """PATCH válido em meta ACTIVE → 200."""
    goal = _mock_goal()
    updated = _mock_goal()
    tracker = MagicMock()
    tracker._load.return_value = goal
    tracker.update_progress.return_value = updated
    tracker.get_projection.return_value = _mock_projection()

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        with patch("app.goals.router.invalidate_user_cache"):
            resp = client.patch(
                f"/goals/{USER}/{GOAL_ID}/progress",
                json={"amount_to_add": 500.0},
            )
    assert resp.status_code == 200


# ── DELETE /goals/{user_id}/{goal_id} ─────────────────────────────────────────

def test_abandon_goal_not_found():
    """Goal inexistente → 404."""
    tracker = MagicMock()
    tracker._load.side_effect = LookupError("not found")

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        resp = client.delete(f"/goals/{USER}/{GOAL_ID}")
    assert resp.status_code == 404


def test_abandon_goal_success():
    """DELETE válido → 200 com mensagem."""
    goal = _mock_goal()
    abandoned = _mock_goal(status="ABANDONED")
    tracker = MagicMock()
    tracker._load.return_value = goal
    tracker.abandon_goal.return_value = abandoned

    with patch("app.goals.router._build_goal_tracker", return_value=tracker):
        with patch("app.goals.router.invalidate_user_cache"):
            resp = client.delete(f"/goals/{USER}/{GOAL_ID}")
    assert resp.status_code == 200
    assert "message" in resp.json()
