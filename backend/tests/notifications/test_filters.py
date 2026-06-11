import pytest
from datetime import datetime, timezone
from app.notifications.notifier import Notification
from app.notifications.relevance_filter import NotificationRelevanceFilter

def _make(type: str, priority: str, metadata: dict) -> Notification:
    return Notification(
        id="x", type=type, priority=priority,
        title="T", message="M",
        generated_at=datetime.now(timezone.utc),
        metadata=metadata,
    )

_rf = NotificationRelevanceFilter()


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


