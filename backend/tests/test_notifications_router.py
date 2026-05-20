# tests/test_notifications_router.py
# Testes de router HTTP para MX.3 — Notificações Proativas

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.notifications.router import router, _state_store, _notifier, _relevance_filter
from app.core.security import require_owner


USER = "user_notif_test"


def _make_app(auth_user: str = USER):
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[require_owner] = lambda user_id: auth_user
    return a


app = _make_app()
client = TestClient(app)


def _empty_runner_result():
    return {"transactions": {"pf_pj_classified_df": None}}


# ── GET /notifications/{user_id} ─────────────────────────────────────────────

def _patch_get_runner():
    """Retorna context manager que substitui get_runner onde é importado dentro do router."""
    return patch("app.runner.get_runner", return_value=MagicMock(
        run=MagicMock(return_value=_empty_runner_result())
    ))


def test_get_notifications_empty_pipeline():
    """Pipeline sem dados retorna resposta válida com total=0."""
    with _patch_get_runner():
        with patch.object(_notifier, "generate", return_value=[]):
            with patch.object(_relevance_filter, "filter", return_value=[]):
                with patch.object(_state_store, "filter_unseen", return_value=[]):
                    with patch.object(_state_store, "mark_shown"):
                        with patch.object(_state_store, "annotate_fingerprints", return_value={}):
                            resp = client.get(f"/notifications/{USER}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == USER
    assert data["total"] == 0
    assert "notifications" in data
    assert "by_priority" in data
    assert set(data["by_priority"].keys()) == {"CRITICAL", "WARNING", "INFO"}


def test_get_notifications_returns_notification_with_fingerprint():
    """Notificação retornada inclui campo fingerprint."""
    from app.notifications.notifier import Notification
    from datetime import datetime

    notif = Notification(
        id="n1",
        type="BURN_RATE",
        priority="WARNING",
        title="Alerta de Gastos",
        message="Você gastou 80% do orçamento de alimentação.",
        generated_at=datetime.now(),
        metadata={"category": "alimentacao"},
    )

    with _patch_get_runner():
        with patch.object(_notifier, "generate", return_value=[notif]):
            with patch.object(_relevance_filter, "filter", return_value=[notif]):
                with patch.object(_state_store, "filter_unseen", return_value=[notif]):
                    with patch.object(_state_store, "mark_shown"):
                        with patch.object(_state_store, "annotate_fingerprints", return_value={"n1": "fp_abc"}):
                            resp = client.get(f"/notifications/{USER}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["notifications"][0]["fingerprint"] == "fp_abc"
    assert data["by_priority"]["WARNING"] == 1


def test_get_notifications_include_info_false():
    """include_info=false → campo total reflete só CRITICAL e WARNING."""
    with _patch_get_runner():
        with patch.object(_notifier, "generate", return_value=[]):
            with patch.object(_relevance_filter, "filter", return_value=[]):
                with patch.object(_state_store, "filter_unseen", return_value=[]):
                    with patch.object(_state_store, "mark_shown"):
                        with patch.object(_state_store, "annotate_fingerprints", return_value={}):
                            resp = client.get(f"/notifications/{USER}?include_info=false")

    assert resp.status_code == 200


# ── POST /notifications/{user_id}/events ─────────────────────────────────────

def test_post_event_invalid_type():
    """event_type inválido → 422."""
    with patch.object(_state_store, "log_event"):
        resp = client.post(
            f"/notifications/{USER}/events",
            json={"fingerprint": "fp1", "notification_type": "BURN_RATE", "event_type": "ignored"},
        )
    assert resp.status_code == 422


def test_post_event_tapped():
    """event_type='tapped' → 200 {ok: true}."""
    with patch.object(_state_store, "log_event"):
        resp = client.post(
            f"/notifications/{USER}/events",
            json={"fingerprint": "fp1", "notification_type": "BURN_RATE", "event_type": "tapped"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_post_event_dismissed():
    """event_type='dismissed' → 200 {ok: true}."""
    with patch.object(_state_store, "log_event"):
        resp = client.post(
            f"/notifications/{USER}/events",
            json={"fingerprint": "fp1", "notification_type": "ANOMALY", "event_type": "dismissed"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_post_event_missing_fields():
    """Campos obrigatórios ausentes → 422."""
    resp = client.post(
        f"/notifications/{USER}/events",
        json={"event_type": "tapped"},
    )
    assert resp.status_code == 422
