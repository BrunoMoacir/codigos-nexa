import pytest
import os
import tempfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.notifications.state_store import NotificationStateStore, compute_fingerprint
from app.notifications.notifier import NotificationContext, Notification
from app.notifications.router import router as notif_router
from app.core.security import get_current_user, require_owner

def _make(type: str, priority: str, metadata: dict) -> Notification:
    from datetime import datetime, timezone
    return Notification(
        id="x", type=type, priority=priority,
        title="T", message="M",
        generated_at=datetime.now(timezone.utc),
        metadata=metadata,
    )

_app = FastAPI()
_app.include_router(notif_router)
_app.dependency_overrides[get_current_user] = lambda: "test_user"
_app.dependency_overrides[require_owner] = lambda: "test_user"
_client = TestClient(_app)

from app.notifications.notifier import ProactiveNotifier, BurnRateCategoryInput, AnomalyInput, CardOpportunityInput, ScoreChangeInput, SafeToSpendInput, GoalProgressInput
from app.notifications.relevance_filter import NotificationRelevanceFilter
_rf = NotificationRelevanceFilter()

from app.notifications.state_store import NotificationStateStore, compute_fingerprint
import tempfile, os


def _store_with_temp_db() -> NotificationStateStore:
    """Cria um store apontando para um DuckDB temporário."""
    store = NotificationStateStore()
    tmp = tempfile.mktemp(suffix=".duckdb")

    def _temp_conn():
        import duckdb
        return duckdb.connect(tmp)

    store._conn = _temp_conn
    return store, tmp


def test_compute_fingerprint_stable():
    """Mesmo user_id + notificação = mesmo fingerprint."""
    n = _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0})
    fp1 = compute_fingerprint("user_a", n)
    fp2 = compute_fingerprint("user_a", n)
    assert fp1 == fp2


def test_compute_fingerprint_user_isolation():
    """Usuários diferentes → fingerprints diferentes."""
    n = _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0})
    assert compute_fingerprint("user_a", n) != compute_fingerprint("user_b", n)


def test_compute_fingerprint_type_isolation():
    """Tipos diferentes → fingerprints diferentes."""
    n1 = _make("BURN_RATE_HIGH",   "WARNING", {"category": "lazer"})
    n2 = _make("ANOMALY_DETECTED", "WARNING", {"category": "lazer"})
    assert compute_fingerprint("u", n1) != compute_fingerprint("u", n2)


def test_state_store_filter_unseen_first_time():
    """Notificação vista pela primeira vez não é suprimida."""
    store, tmp = _store_with_temp_db()
    try:
        n = _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0})
        result = store.filter_unseen("user_x", [n])
        assert len(result) == 1
    finally:
        os.unlink(tmp)


def test_state_store_suppresses_after_mark_shown():
    """Notificação marcada como vista é suprimida na próxima consulta."""
    store, tmp = _store_with_temp_db()
    try:
        n = _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0})
        store.mark_shown("user_x", [n])
        result = store.filter_unseen("user_x", [n])
        assert result == []
    finally:
        os.unlink(tmp)


def test_state_store_critical_never_suppressed():
    """CRITICAL passa mesmo após mark_shown."""
    store, tmp = _store_with_temp_db()
    try:
        n = _make("SAFE_TO_SPEND_LOW", "CRITICAL", {"daily_safe": 10.0})
        store.mark_shown("user_x", [n])
        result = store.filter_unseen("user_x", [n])
        assert len(result) == 1
    finally:
        os.unlink(tmp)


def test_state_store_different_users_isolated():
    """Mark shown para user_a não suprime para user_b."""
    store, tmp = _store_with_temp_db()
    try:
        n = _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0})
        store.mark_shown("user_a", [n])
        result = store.filter_unseen("user_b", [n])
        assert len(result) == 1
    finally:
        os.unlink(tmp)


def test_state_store_log_event_and_analytics():
    """log_event registra evento; get_analytics_summary retorna contagem."""
    store, tmp = _store_with_temp_db()
    try:
        n = _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 50.0})
        fp = compute_fingerprint("u", n)
        store.mark_shown("u", [n])
        store.log_event("u", fp, "CARD_OPPORTUNITY", "dismissed")
        summary = store.get_analytics_summary("u", days=30)
        assert "CARD_OPPORTUNITY" in summary
        assert summary["CARD_OPPORTUNITY"].get("dismissed", 0) >= 1
    finally:
        os.unlink(tmp)


def test_state_store_invalid_event_type_ignored():
    """Evento inválido não lança exceção (log + ignora); DB pode não ser criado."""
    store, tmp = _store_with_temp_db()
    try:
        store.log_event("u", "fp123", "BURN_RATE_HIGH", "INVALID_EVENT")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# — endpoint de eventos —

def test_api_events_endpoint_tapped():
    resp = _client.post("/notifications/test_user/events", json={
        "fingerprint": "abc12345",
        "notification_type": "CARD_OPPORTUNITY",
        "event_type": "tapped",
    })
    assert resp.status_code == 200


def test_api_events_endpoint_dismissed():
    resp = _client.post("/notifications/test_user/events", json={
        "fingerprint": "abc12345",
        "notification_type": "BURN_RATE_HIGH",
        "event_type": "dismissed",
    })
    assert resp.status_code == 200


def test_api_events_endpoint_invalid_event_type():
    resp = _client.post("/notifications/test_user/events", json={
        "fingerprint": "abc12345",
        "notification_type": "BURN_RATE_HIGH",
        "event_type": "ignored",
    })
    assert resp.status_code == 422


def test_api_response_includes_fingerprint():
    """Cada notificação na resposta deve ter um campo fingerprint."""
    resp = _client.get("/notifications/test_user?monthly_income=5000")
    assert resp.status_code == 200
    for n in resp.json()["notifications"]:
        assert "fingerprint" in n
        assert isinstance(n["fingerprint"], str)


# — integração com ProactiveNotifier —

def test_filter_integrated_with_notifier():
    """
    Gera notificações via ProactiveNotifier e valida:
    - CRITICAL passam todos
    - WARNING+INFO limitados a _MAX_NON_CRITICAL (4)
    - Ordem CRITICAL → WARNING → INFO preservada
    """
    ctx = NotificationContext(
        burn_rate_categories=[
            BurnRateCategoryInput("alimentacao", 920.0, 1000.0, 0.92, 20),  # CRITICAL ✓
            BurnRateCategoryInput("lazer",        760.0, 1000.0, 0.76, 20),  # WARNING  ✓
            BurnRateCategoryInput("transporte",   750.0, 1000.0, 0.75, 20),  # WARNING  ✓ (type cap: 2)
        ],
        anomalies=[
            AnomalyInput("Amazon",  800.0, 4.0, "UNUSUAL_AMOUNT", "Alto"),   # CRITICAL ✓
            AnomalyInput("iFood",   150.0, 2.3, "UNUSUAL_AMOUNT", "Baixo"),  # descartado (factor<2.5)
        ],
        card_opportunities=[
            CardOpportunityInput("Nubank", 20.0, "reason"),  # descartado (gain<30)
        ],
        score_change=ScoreChangeInput(60.0, 63.0, 3.0),      # descartado (delta<5)
        safe_to_spend=SafeToSpendInput(30.0, 900.0),          # CRITICAL ✓
        goal_progress=[
            GoalProgressInput("Casa",   "g1", 25.0, 100000.0),  # descartado (25% milestone)
            GoalProgressInput("Viagem", "g2", 75.0,   5000.0),  # INFO ✓
        ],
    )

    raw = ProactiveNotifier().generate(ctx)
    filtered = _rf.filter(raw)

    priorities = [n.priority for n in filtered]

    # CRITICAL passa tudo (3 neste contexto)
    assert sum(1 for p in priorities if p == "CRITICAL") == 3

    # Não-CRITICAL ≤ 4
    assert sum(1 for p in priorities if p != "CRITICAL") <= 4

    # Ordem CRITICAL → WARNING → INFO preservada
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    assert priorities == sorted(priorities, key=lambda p: order[p])
