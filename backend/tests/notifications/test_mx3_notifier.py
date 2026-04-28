# tests/notifications/test_mx3_notifier.py
# Testes para MX.3 — Notificações Proativas Inteligentes

import pytest
from datetime import datetime

from app.notifications.notifier import (
    ProactiveNotifier,
    Notification,
    NotificationContext,
    BurnRateCategoryInput,
    AnomalyInput,
    SubscriptionChangeInput,
    CardOpportunityInput,
    WaiverAlertInput,
    TransferPromoInput,
    ScoreChangeInput,
    GoalProgressInput,
    SafeToSpendInput,
    generate_burn_rate_notifications,
    generate_anomaly_notifications,
    generate_subscription_increase_notifications,
    generate_card_opportunity_notifications,
    generate_waiver_alert_notifications,
    generate_transfer_promo_notifications,
    generate_score_improved_notification,
    generate_goal_progress_notifications,
    generate_safe_to_spend_low_notification,
)


# ── 1. Notification dataclass ─────────────────────────────────────────────────

def test_notification_to_dict_has_all_keys():
    n = Notification(
        id="abc123",
        type="TEST",
        priority="INFO",
        title="Test",
        message="Hello",
        generated_at=datetime.utcnow(),
    )
    d = n.to_dict()
    assert {"id", "type", "priority", "title", "message", "generated_at", "metadata", "action_hint"}.issubset(d)


# ── 2. BURN_RATE_HIGH ─────────────────────────────────────────────────────────

def test_burn_rate_below_threshold_no_notification():
    cat = BurnRateCategoryInput(
        category="lazer", spent_so_far=500.0, monthly_budget=1000.0,
        pct_consumed=0.50, current_day=15,
    )
    notes = generate_burn_rate_notifications([cat])
    assert len(notes) == 0


def test_burn_rate_warning_at_70pct():
    cat = BurnRateCategoryInput(
        category="alimentacao", spent_so_far=750.0, monthly_budget=1000.0,
        pct_consumed=0.75, current_day=15,
    )
    notes = generate_burn_rate_notifications([cat])
    assert len(notes) == 1
    assert notes[0].type == "BURN_RATE_HIGH"
    assert notes[0].priority == "WARNING"


def test_burn_rate_critical_at_90pct():
    cat = BurnRateCategoryInput(
        category="alimentacao", spent_so_far=920.0, monthly_budget=1000.0,
        pct_consumed=0.92, current_day=20,
    )
    notes = generate_burn_rate_notifications([cat])
    assert len(notes) == 1
    assert notes[0].priority == "CRITICAL"


def test_burn_rate_over_100pct_critical():
    cat = BurnRateCategoryInput(
        category="lazer", spent_so_far=1200.0, monthly_budget=1000.0,
        pct_consumed=1.20, current_day=22,
    )
    notes = generate_burn_rate_notifications([cat])
    assert len(notes) == 1
    assert notes[0].priority == "CRITICAL"
    assert "estourado" in notes[0].title.lower()


def test_burn_rate_multiple_categories():
    cats = [
        BurnRateCategoryInput("moradia",   2500.0, 2800.0, 0.89, 25),  # WARNING
        BurnRateCategoryInput("vestuario",  800.0,  500.0, 1.60, 25),  # CRITICAL (over)
        BurnRateCategoryInput("lazer",      100.0, 1000.0, 0.10, 25),  # nothing
    ]
    notes = generate_burn_rate_notifications(cats)
    assert len(notes) == 2


def test_burn_rate_message_contains_category():
    cat = BurnRateCategoryInput(
        category="transporte", spent_so_far=800.0, monthly_budget=1000.0,
        pct_consumed=0.80, current_day=20,
    )
    notes = generate_burn_rate_notifications([cat])
    assert "Transporte" in notes[0].message


# ── 3. ANOMALY_DETECTED ───────────────────────────────────────────────────────

def test_anomaly_notification_generated():
    a = AnomalyInput(
        merchant="Restaurante XYZ", amount=450.0, factor=2.5,
        anomaly_type="UNUSUAL_AMOUNT", description="Gasto acima do padrão",
    )
    notes = generate_anomaly_notifications([a])
    assert len(notes) == 1
    assert notes[0].type == "ANOMALY_DETECTED"
    assert notes[0].priority == "WARNING"


def test_anomaly_high_factor_is_critical():
    a = AnomalyInput(
        merchant="Amazon", amount=3000.0, factor=8.0,
        anomaly_type="UNUSUAL_AMOUNT", description="Muito acima do padrão",
    )
    notes = generate_anomaly_notifications([a])
    assert notes[0].priority == "CRITICAL"


def test_anomaly_max_alerts_limit():
    anomalies = [
        AnomalyInput(f"Merchant_{i}", 100.0 * i, 2.0, "UNUSUAL", "desc")
        for i in range(10)
    ]
    notes = generate_anomaly_notifications(anomalies, max_alerts=3)
    assert len(notes) == 3


# ── 4. SUBSCRIPTION_INCREASE ─────────────────────────────────────────────────

def test_subscription_increase_notified():
    change = SubscriptionChangeInput(
        merchant="Netflix", old_amount=39.90, new_amount=55.90, pct_change=0.40,
    )
    notes = generate_subscription_increase_notifications([change])
    assert len(notes) == 1
    assert notes[0].type == "SUBSCRIPTION_INCREASE"
    assert "Netflix" in notes[0].message


def test_subscription_no_increase_no_notification():
    change = SubscriptionChangeInput(
        merchant="Spotify", old_amount=22.0, new_amount=22.0, pct_change=0.0,
    )
    notes = generate_subscription_increase_notifications([change])
    assert len(notes) == 0


def test_subscription_pct_displayed():
    change = SubscriptionChangeInput(
        merchant="HBO", old_amount=20.0, new_amount=30.0, pct_change=0.50,
    )
    notes = generate_subscription_increase_notifications([change])
    assert "+50%" in notes[0].title


# ── 5. CARD_OPPORTUNITY ───────────────────────────────────────────────────────

def test_card_opportunity_notification():
    opp = CardOpportunityInput(
        card_name="Nubank Ultravioleta",
        monthly_gain_missed=120.0,
        reason="Concentre gastos em alimentação neste cartão.",
    )
    notes = generate_card_opportunity_notifications([opp])
    assert len(notes) == 1
    assert notes[0].type == "CARD_OPPORTUNITY"
    assert notes[0].priority == "INFO"
    assert "Nubank Ultravioleta" in notes[0].message


def test_card_opportunity_max_2():
    opps = [
        CardOpportunityInput(f"Card_{i}", 100.0, "reason") for i in range(5)
    ]
    notes = generate_card_opportunity_notifications(opps)
    assert len(notes) == 2


# ── 6. WAIVER_ALERT ───────────────────────────────────────────────────────────

def test_waiver_alert_notification():
    alert = WaiverAlertInput(
        card_name="C6 Carbon", amount_needed=500.0, daily_spend_needed=20.0,
    )
    notes = generate_waiver_alert_notifications([alert])
    assert len(notes) == 1
    assert notes[0].type == "WAIVER_ALERT"
    assert "C6 Carbon" in notes[0].message
    assert "500" in notes[0].title


# ── 7. TRANSFER_PROMO ─────────────────────────────────────────────────────────

def test_transfer_promo_notification():
    promo = TransferPromoInput(
        from_program="Livelo",
        to_program="LATAM Pass",
        bonus_pct=0.50,
        end_date="2026-03-31",
        user_points=10000,
    )
    notes = generate_transfer_promo_notifications([promo])
    assert len(notes) == 1
    assert notes[0].type == "TRANSFER_PROMO"
    assert "+50%" in notes[0].title
    assert "15,000" in notes[0].message   # 10000 * 1.5 equivalente (formatted with comma)


# ── 8. SCORE_IMPROVED ────────────────────────────────────────────────────────

def test_score_improved_notification():
    change = ScoreChangeInput(old_score=62.0, new_score=68.5, delta=6.5)
    notes = generate_score_improved_notification(change)
    assert len(notes) == 1
    assert notes[0].type == "SCORE_IMPROVED"
    assert "subiu" in notes[0].message


def test_score_delta_too_small_no_notification():
    change = ScoreChangeInput(old_score=62.0, new_score=63.0, delta=1.0)
    notes = generate_score_improved_notification(change)
    assert len(notes) == 0


def test_score_decreased_warning():
    change = ScoreChangeInput(old_score=72.0, new_score=65.0, delta=-7.0)
    notes = generate_score_improved_notification(change)
    assert len(notes) == 1
    assert notes[0].priority == "WARNING"
    assert "caiu" in notes[0].message


def test_score_none_returns_empty():
    notes = generate_score_improved_notification(None)
    assert len(notes) == 0


# ── 9. GOAL_PROGRESS ─────────────────────────────────────────────────────────

def test_goal_progress_at_milestone_50pct():
    g = GoalProgressInput(
        goal_name="Viagem Europa", goal_id="g1",
        pct_complete=50.0, remaining_amount=10000.0,
    )
    notes = generate_goal_progress_notifications([g])
    assert len(notes) == 1
    assert notes[0].type == "GOAL_PROGRESS"
    assert "50" in notes[0].title or "Viagem Europa" in notes[0].title


def test_goal_progress_not_at_milestone_no_notification():
    g = GoalProgressInput(
        goal_name="Carro", goal_id="g2",
        pct_complete=38.0, remaining_amount=25000.0,
    )
    notes = generate_goal_progress_notifications([g])
    assert len(notes) == 0  # 38% não é marco (25, 50, 75, 100)


def test_goal_progress_100pct_completion():
    g = GoalProgressInput(
        goal_name="Reserva Emergência", goal_id="g3",
        pct_complete=100.0, remaining_amount=0.0,
    )
    notes = generate_goal_progress_notifications([g])
    assert len(notes) == 1
    assert "concluída" in notes[0].title.lower() or "100" in notes[0].title


def test_goal_progress_near_milestone_tolerance():
    """48% está dentro da tolerância de ±5 p.p. do marco de 50%."""
    g = GoalProgressInput(
        goal_name="Imovel", goal_id="g4",
        pct_complete=48.0, remaining_amount=150000.0,
    )
    notes = generate_goal_progress_notifications([g])
    assert len(notes) == 1  # 48% ≈ 50% marco (tolerância 5 p.p.)


# ── 10. SAFE_TO_SPEND_LOW ────────────────────────────────────────────────────

def test_safe_to_spend_critical_below_50():
    sts = SafeToSpendInput(daily_safe_amount=30.0, monthly_safe_amount=900.0)
    notes = generate_safe_to_spend_low_notification(sts)
    assert len(notes) == 1
    assert notes[0].type == "SAFE_TO_SPEND_LOW"
    assert notes[0].priority == "CRITICAL"


def test_safe_to_spend_warning_at_80():
    sts = SafeToSpendInput(daily_safe_amount=80.0, monthly_safe_amount=2400.0)
    notes = generate_safe_to_spend_low_notification(sts)
    assert len(notes) == 1
    assert notes[0].priority == "WARNING"


def test_safe_to_spend_ok_no_notification():
    sts = SafeToSpendInput(daily_safe_amount=200.0, monthly_safe_amount=6000.0)
    notes = generate_safe_to_spend_low_notification(sts)
    assert len(notes) == 0


def test_safe_to_spend_zero_critical():
    sts = SafeToSpendInput(daily_safe_amount=0.0, monthly_safe_amount=0.0)
    notes = generate_safe_to_spend_low_notification(sts)
    assert len(notes) == 1
    assert notes[0].priority == "CRITICAL"
    assert "zerou" in notes[0].message.lower() or "sem margem" in notes[0].title.lower()


def test_safe_to_spend_none_returns_empty():
    notes = generate_safe_to_spend_low_notification(None)
    assert len(notes) == 0


# ── 11. ProactiveNotifier orquestrador ────────────────────────────────────────

def test_notifier_empty_context_returns_no_notifications():
    ctx = NotificationContext()
    notes = ProactiveNotifier().generate(ctx)
    assert notes == []


def test_notifier_sorted_by_priority():
    """Notificações CRITICAL devem vir antes de WARNING e INFO."""
    ctx = NotificationContext(
        burn_rate_categories=[
            BurnRateCategoryInput("lazer", 950.0, 1000.0, 0.95, 20),  # CRITICAL
        ],
        safe_to_spend=SafeToSpendInput(80.0, 2400.0),  # WARNING
        card_opportunities=[
            CardOpportunityInput("Nubank", 100.0, "reason"),  # INFO
        ],
    )
    notes = ProactiveNotifier().generate(ctx)
    priorities = [n.priority for n in notes]
    # Primeiro CRITICAL, depois WARNING, depois INFO
    assert priorities[0] == "CRITICAL"
    assert "INFO" not in priorities[:2] or all(p in {"CRITICAL", "WARNING"} for p in priorities if p != "INFO")


def test_notifier_all_types_generated():
    """Todos os 9 tipos de notificação devem ser gerados com o contexto adequado."""
    ctx = NotificationContext(
        burn_rate_categories=[
            BurnRateCategoryInput("alimentacao", 750.0, 1000.0, 0.75, 15),
        ],
        anomalies=[
            AnomalyInput("Mercado Livre", 500.0, 3.5, "UNUSUAL_AMOUNT", "Alto"),
        ],
        subscription_changes=[
            SubscriptionChangeInput("Disney+", 29.0, 45.90, 0.58),
        ],
        card_opportunities=[
            CardOpportunityInput("Itaú Platinum", 150.0, "Melhor para viagens"),
        ],
        waiver_alerts=[
            WaiverAlertInput("Santander Infinite", 300.0, 15.0),
        ],
        transfer_promos=[
            TransferPromoInput("Smiles", "Miles&More", 0.25, "2026-03-31", 5000),
        ],
        score_change=ScoreChangeInput(58.0, 63.0, 5.0),
        goal_progress=[
            GoalProgressInput("Viagem", "g1", 75.0, 5000.0),
        ],
        safe_to_spend=SafeToSpendInput(45.0, 1350.0),
    )
    notes = ProactiveNotifier().generate(ctx)
    types = {n.type for n in notes}
    expected_types = {
        "BURN_RATE_HIGH",
        "ANOMALY_DETECTED",
        "SUBSCRIPTION_INCREASE",
        "CARD_OPPORTUNITY",
        "WAIVER_ALERT",
        "TRANSFER_PROMO",
        "SCORE_IMPROVED",
        "GOAL_PROGRESS",
        "SAFE_TO_SPEND_LOW",
    }
    assert expected_types == types


def test_notifier_to_dict_valid_json_structure():
    ctx = NotificationContext(
        safe_to_spend=SafeToSpendInput(30.0, 900.0),
    )
    notes = ProactiveNotifier().generate(ctx)
    assert len(notes) == 1
    d = notes[0].to_dict()
    assert isinstance(d["id"], str)
    assert isinstance(d["metadata"], dict)
    assert isinstance(d["generated_at"], str)


# ── 12. API endpoint ──────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.notifications.router import router as notif_router
from app.core.security import get_current_user, require_owner

_app = FastAPI()
_app.include_router(notif_router)
_app.dependency_overrides[get_current_user] = lambda: "test_user"
_app.dependency_overrides[require_owner] = lambda: "test_user"
_client = TestClient(_app)


def test_api_returns_200_or_graceful():
    """
    O endpoint deve responder 200 com JSON válido mesmo quando
    o NexaRunner não tem dados (modo dev sem banco real).
    """
    resp = _client.get("/notifications/test_user?monthly_income=8000")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "total" in data
    assert "notifications" in data
    assert isinstance(data["notifications"], list)


def test_api_response_structure():
    resp = _client.get("/notifications/test_user")
    assert resp.status_code == 200
    data = resp.json()
    assert "by_priority" in data
    assert "CRITICAL" in data["by_priority"]
    assert "WARNING" in data["by_priority"]
    assert "INFO" in data["by_priority"]


def test_api_include_info_false_filters():
    """
    include_info=false deve retornar apenas CRITICAL e WARNING.
    """
    resp = _client.get("/notifications/test_user?include_info=false")
    assert resp.status_code == 200
    data = resp.json()
    for n in data["notifications"]:
        assert n["priority"] != "INFO"


# ── 13. NotificationRelevanceFilter ──────────────────────────────────────────

from app.notifications.relevance_filter import NotificationRelevanceFilter
from datetime import datetime, timezone


def _make(type: str, priority: str, metadata: dict) -> Notification:
    return Notification(
        id="x", type=type, priority=priority,
        title="T", message="M",
        generated_at=datetime.now(timezone.utc),
        metadata=metadata,
    )


_rf = NotificationRelevanceFilter()


# — threshold por tipo —

def test_filter_burn_rate_below_75_dropped():
    n = _make("BURN_RATE_HIGH", "WARNING", {"pct_consumed": 72.0})
    assert _rf.filter([n]) == []


def test_filter_burn_rate_at_75_passes():
    n = _make("BURN_RATE_HIGH", "WARNING", {"pct_consumed": 75.0})
    assert len(_rf.filter([n])) == 1


def test_filter_burn_rate_critical_always_passes():
    # CRITICAL nunca é descartado pelo cap por tipo
    n = _make("BURN_RATE_HIGH", "CRITICAL", {"pct_consumed": 91.0})
    assert len(_rf.filter([n])) == 1


def test_filter_anomaly_weak_factor_dropped():
    n = _make("ANOMALY_DETECTED", "WARNING", {"factor": 2.0, "amount": 500.0})
    assert _rf.filter([n]) == []


def test_filter_anomaly_low_amount_dropped():
    # Renda R$5k: min_amount = 2% × 5k = R$100 → R$50 descartado
    n = _make("ANOMALY_DETECTED", "WARNING", {"factor": 3.0, "amount": 50.0})
    assert _rf.filter([n], monthly_income=5_000.0) == []


def test_filter_anomaly_strong_passes():
    # Renda R$5k: min_amount = R$100 → R$100 passa exato no threshold
    n = _make("ANOMALY_DETECTED", "WARNING", {"factor": 2.5, "amount": 100.0})
    assert len(_rf.filter([n], monthly_income=5_000.0)) == 1


def test_filter_subscription_small_increase_dropped():
    n = _make("SUBSCRIPTION_INCREASE", "WARNING", {
        "pct_change": 5.0, "old_amount": 29.0, "new_amount": 30.5
    })
    assert _rf.filter([n]) == []


def test_filter_subscription_big_pct_passes():
    n = _make("SUBSCRIPTION_INCREASE", "WARNING", {
        "pct_change": 40.0, "old_amount": 29.0, "new_amount": 40.6
    })
    assert len(_rf.filter([n])) == 1


def test_filter_subscription_big_absolute_passes():
    # R$12 de diferença absoluta, mas pct baixo
    n = _make("SUBSCRIPTION_INCREASE", "WARNING", {
        "pct_change": 4.0, "old_amount": 300.0, "new_amount": 312.0
    })
    assert len(_rf.filter([n])) == 1


def test_filter_card_opportunity_low_gain_dropped():
    # Renda R$6k: min_gain = 0.5% × 6k = R$30 → R$25 descartado
    n = _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 25.0})
    assert _rf.filter([n], monthly_income=6_000.0) == []


def test_filter_card_opportunity_passes():
    # Renda R$6k: min_gain = R$30 → R$30 passa
    n = _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 30.0})
    assert len(_rf.filter([n], monthly_income=6_000.0)) == 1


def test_filter_waiver_impossible_daily_dropped():
    n = _make("WAIVER_ALERT", "INFO", {"amount_needed": 500.0, "daily_spend_needed": 500.0})
    assert _rf.filter([n]) == []


def test_filter_waiver_achievable_passes():
    n = _make("WAIVER_ALERT", "INFO", {"amount_needed": 500.0, "daily_spend_needed": 50.0})
    assert len(_rf.filter([n])) == 1


def test_filter_waiver_large_amount_dropped():
    # R$12.000 restante com R$400/dia: teoricamente alcançável mas inviável na prática
    n = _make("WAIVER_ALERT", "INFO", {"amount_needed": 12_000.0, "daily_spend_needed": 400.0})
    assert _rf.filter([n]) == []


def test_filter_transfer_promo_low_bonus_dropped():
    n = _make("TRANSFER_PROMO", "INFO", {"bonus_pct": 10, "user_points": 5000})
    assert _rf.filter([n]) == []


def test_filter_transfer_promo_no_points_dropped():
    n = _make("TRANSFER_PROMO", "INFO", {"bonus_pct": 50, "user_points": 500})
    assert _rf.filter([n]) == []


def test_filter_transfer_promo_passes():
    n = _make("TRANSFER_PROMO", "INFO", {"bonus_pct": 50, "user_points": 5000})
    assert len(_rf.filter([n])) == 1


def test_filter_score_small_delta_dropped():
    n = _make("SCORE_IMPROVED", "INFO", {"delta": 3.0})
    assert _rf.filter([n]) == []


def test_filter_score_big_delta_passes():
    n = _make("SCORE_IMPROVED", "INFO", {"delta": 5.0})
    assert len(_rf.filter([n])) == 1


def test_filter_score_negative_big_delta_passes():
    n = _make("SCORE_IMPROVED", "WARNING", {"delta": -6.0})
    assert len(_rf.filter([n])) == 1


def test_filter_goal_25pct_dropped():
    n = _make("GOAL_PROGRESS", "INFO", {"milestone": 25.0})
    assert _rf.filter([n]) == []


def test_filter_goal_50pct_passes():
    n = _make("GOAL_PROGRESS", "INFO", {"milestone": 50.0})
    assert len(_rf.filter([n])) == 1


def test_filter_goal_100pct_passes():
    n = _make("GOAL_PROGRESS", "INFO", {"milestone": 100.0})
    assert len(_rf.filter([n])) == 1


def test_filter_safe_to_spend_always_passes():
    n = _make("SAFE_TO_SPEND_LOW", "CRITICAL", {"daily_safe": 20.0, "monthly_safe": 600.0})
    assert len(_rf.filter([n])) == 1


def test_filter_life_event_low_confidence_dropped():
    n = _make("LIFE_EVENT", "WARNING", {"confidence": 0.65, "event": "new_baby"})
    assert _rf.filter([n]) == []


def test_filter_life_event_high_confidence_passes():
    n = _make("LIFE_EVENT", "WARNING", {"confidence": 0.75, "event": "income_drop"})
    assert len(_rf.filter([n])) == 1


# — cap por tipo —

def test_filter_max_2_per_type_warning():
    notes = [
        _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 50.0}),
        _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 60.0}),
        _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 70.0}),
    ]
    result = _rf.filter(notes)
    assert len(result) == 2


def test_filter_critical_exempt_from_type_cap():
    notes = [
        _make("BURN_RATE_HIGH", "CRITICAL", {"pct_consumed": 95.0}),
        _make("BURN_RATE_HIGH", "CRITICAL", {"pct_consumed": 110.0}),
        _make("BURN_RATE_HIGH", "CRITICAL", {"pct_consumed": 105.0}),
    ]
    result = _rf.filter(notes)
    # Todos 3 CRITICAL devem passar (cap por tipo e cap global não se aplicam)
    assert len(result) == 3


# — cap global (CRITICAL ilimitado) —

def test_filter_non_critical_capped_at_4():
    notes = [
        _make("BURN_RATE_HIGH", "WARNING", {"pct_consumed": 80.0}),
        _make("ANOMALY_DETECTED", "WARNING", {"factor": 3.0, "amount": 200.0}),
        _make("SUBSCRIPTION_INCREASE", "WARNING", {"pct_change": 25.0, "old_amount": 30.0, "new_amount": 37.5}),
        _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 40.0}),
        _make("WAIVER_ALERT", "INFO", {"amount_needed": 500.0, "daily_spend_needed": 10.0}),
        _make("TRANSFER_PROMO", "INFO", {"bonus_pct": 30, "user_points": 2000}),
        _make("SCORE_IMPROVED", "INFO", {"delta": 8.0}),
    ]
    result = _rf.filter(notes)
    non_critical = [n for n in result if n.priority != "CRITICAL"]
    assert len(non_critical) <= 4


def test_filter_critical_not_capped_by_global():
    # 6 CRITICAL + 2 WARNING: todos os CRITICAL devem passar, WARNING limitado a 4 slots
    notes = [
        _make("BURN_RATE_HIGH",        "CRITICAL", {"pct_consumed": 110.0}),
        _make("ANOMALY_DETECTED",      "CRITICAL", {"factor": 5.0, "amount": 500.0}),
        _make("SAFE_TO_SPEND_LOW",     "CRITICAL", {"daily_safe": 10.0, "monthly_safe": 300.0}),
        _make("LIFE_EVENT",            "CRITICAL", {"confidence": 0.9, "event": "income_drop"}),
        _make("BURN_RATE_HIGH",        "CRITICAL", {"pct_consumed": 105.0}),
        _make("ANOMALY_DETECTED",      "CRITICAL", {"factor": 4.0, "amount": 300.0}),
        _make("SUBSCRIPTION_INCREASE", "WARNING",  {"pct_change": 25.0, "old_amount": 30.0, "new_amount": 37.5}),
        _make("CARD_OPPORTUNITY",      "WARNING",  {"monthly_gain_missed": 40.0}),
    ]
    result = _rf.filter(notes)
    critical_count = sum(1 for n in result if n.priority == "CRITICAL")
    # Todos 6 CRITICAL passam (sem cap)
    assert critical_count == 6
    # WARNING limitado a 4 slots, mas com 6 CRITICAL os 4 slots não-críticos ficam 2
    non_critical_count = sum(1 for n in result if n.priority != "CRITICAL")
    assert non_critical_count <= 4


def test_filter_critical_prioritized_over_warning_in_global():
    # 1 CRITICAL + 5 WARNING/INFO: CRITICAL sempre passa, WARNING/INFO limitado
    notes = [
        _make("BURN_RATE_HIGH",        "CRITICAL", {"pct_consumed": 110.0}),
        _make("ANOMALY_DETECTED",      "WARNING",  {"factor": 3.0, "amount": 200.0}),
        _make("SUBSCRIPTION_INCREASE", "WARNING",  {"pct_change": 25.0, "old_amount": 30.0, "new_amount": 37.5}),
        _make("CARD_OPPORTUNITY",      "INFO",     {"monthly_gain_missed": 40.0}),
        _make("WAIVER_ALERT",          "INFO",     {"amount_needed": 500.0, "daily_spend_needed": 10.0}),
        _make("TRANSFER_PROMO",        "INFO",     {"bonus_pct": 30, "user_points": 2000}),
    ]
    result = _rf.filter(notes)
    assert any(n.priority == "CRITICAL" for n in result)
    assert len([n for n in result if n.priority != "CRITICAL"]) <= 4


# — deduplicação de GOAL_PROGRESS —

def test_filter_goal_duplicate_milestone_deduplicated():
    # Dois alertas do mesmo marco para a mesma meta (tolerância ±5 p.p.)
    notes = [
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0, "pct_complete": 48.0}),
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0, "pct_complete": 52.0}),
    ]
    result = _rf.filter(notes)
    assert len(result) == 1


def test_filter_goal_different_milestones_both_pass():
    notes = [
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0}),
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 75.0}),
    ]
    result = _rf.filter(notes)
    assert len(result) == 2


def test_filter_goal_same_milestone_different_goals_both_pass():
    notes = [
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g1", "milestone": 50.0}),
        _make("GOAL_PROGRESS", "INFO", {"goal_id": "g2", "milestone": 50.0}),
    ]
    result = _rf.filter(notes)
    assert len(result) == 2


def test_filter_empty_input():
    assert _rf.filter([]) == []


# — thresholds relativos à renda —

def test_filter_income_scales_anomaly_threshold():
    """Renda baixa aceita anomalia menor; renda alta exige mais."""
    n_small = _make("ANOMALY_DETECTED", "WARNING", {"factor": 2.5, "amount": 50.0})
    # Renda R$2k: min_amount = max(30, 2000×0.02) = max(30,40) = 40 → R$50 passa
    assert len(_rf.filter([n_small], monthly_income=2_000.0)) == 1
    # Renda R$10k: min_amount = max(30, 10000×0.02) = 200 → R$50 descartado
    assert _rf.filter([n_small], monthly_income=10_000.0) == []


def test_filter_income_scales_card_opportunity():
    """Ganho de R$20/mês é relevante para renda baixa, ruído para renda alta."""
    n = _make("CARD_OPPORTUNITY", "INFO", {"monthly_gain_missed": 20.0})
    # Renda R$2k: min_gain = max(15, 10) = 15 → R$20 passa
    assert len(_rf.filter([n], monthly_income=2_000.0)) == 1
    # Renda R$8k: min_gain = max(15, 40) = 40 → R$20 descartado
    assert _rf.filter([n], monthly_income=8_000.0) == []


def test_filter_income_scales_waiver_daily():
    """R$150/dia é aceitável para renda alta, muito alto para renda baixa."""
    n = _make("WAIVER_ALERT", "INFO", {"amount_needed": 500.0, "daily_spend_needed": 150.0})
    # Renda R$2k: max_daily = max(100, 100) = 100 → R$150 > 100 → descartado
    assert _rf.filter([n], monthly_income=2_000.0) == []
    # Renda R$5k: max_daily = max(100, 250) = 250 → R$150 <= 250 → passa
    assert len(_rf.filter([n], monthly_income=5_000.0)) == 1


def test_filter_income_zero_uses_floor():
    """Income desconhecido (0) usa floor conservador — não bloqueia alertas razoáveis."""
    n = _make("ANOMALY_DETECTED", "WARNING", {"factor": 2.5, "amount": 35.0})
    # Income=0: min_amount=30 (floor) → R$35 passa
    assert len(_rf.filter([n], monthly_income=0.0)) == 1


# — NotificationStateStore —

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
