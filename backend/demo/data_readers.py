"""
demo/data_readers.py — Leitores do footprint completo do usuário.

Consultam DIRETO as tabelas de produção (o que a Nexa realmente armazena),
para o Streamlit mostrar "tudo que o usuário tem e nós guardamos".
"""

from __future__ import annotations

import logging

logger = logging.getLogger("demo.data_readers")


def _rows(sql: str, params: dict) -> list[dict]:
    from sqlalchemy import text
    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            result = db.execute(text(sql), params)
            cols = result.keys()
            return [dict(zip(cols, r)) for r in result.fetchall()]
    except Exception as exc:
        logger.debug("query falhou: %s", exc)
        return []


def accounts(user_id: str) -> list[dict]:
    return _rows(
        "SELECT bank_name, account_type, balance, currency, captured_at"
        " FROM account_balances WHERE user_id = :uid ORDER BY balance DESC",
        {"uid": user_id},
    )


def score_history(user_id: str) -> list[dict]:
    return _rows(
        "SELECT date, health_score, savings_rate, profile_type, safe_to_spend"
        " FROM health_score_history WHERE user_id = :uid ORDER BY date",
        {"uid": user_id},
    )


def fee_history(user_id: str) -> list[dict]:
    return _rows(
        "SELECT month, bank_name, fee_type, amount FROM bank_fee_history"
        " WHERE user_id = :uid ORDER BY month, fee_type",
        {"uid": user_id},
    )


def negotiations(user_id: str) -> list[dict]:
    return _rows(
        "SELECT bank_name, trigger_type, potential_gain, result_status,"
        "       result_gain, generated_at FROM negotiation_history"
        " WHERE user_id = :uid ORDER BY generated_at DESC",
        {"uid": user_id},
    )


def challenges(user_id: str) -> list[dict]:
    from datetime import date

    return _rows(
        "SELECT challenge_type, title, target_label, progress_value, pct_progress,"
        "       status FROM user_challenges WHERE user_id = :uid AND month = :m"
        " ORDER BY challenge_type",
        {"uid": user_id, "m": date.today().strftime("%Y-%m")},
    )


def badges(user_id: str) -> list[dict]:
    return _rows(
        "SELECT badge_type, earned_at FROM user_badges WHERE user_id = :uid"
        " ORDER BY earned_at DESC",
        {"uid": user_id},
    )


def chat_history(user_id: str) -> list[dict]:
    return _rows(
        "SELECT role, content, created_at FROM chat_messages"
        " WHERE user_id = :uid ORDER BY created_at",
        {"uid": user_id},
    )


def context_overrides(user_id: str) -> list[dict]:
    return _rows(
        "SELECT original_context, corrected_context, reason, created_at"
        " FROM context_overrides WHERE user_id = :uid ORDER BY created_at DESC",
        {"uid": user_id},
    )


def goals(user_id: str) -> list[dict]:
    try:
        from app.goals.tracker import GoalTracker

        out = []
        for g in GoalTracker().list_goals(user_id=user_id):
            pct = (g.current_amount / g.target_amount * 100) if g.target_amount else 0
            out.append({
                "name": g.name, "target": g.target_amount, "current": g.current_amount,
                "pct": round(pct, 1), "type": getattr(g, "goal_type", "outros"),
            })
        return out
    except Exception as exc:
        logger.debug("goals: %s", exc)
        return []


# ── inteligência sobre a inteligência (loops de aprendizado, global) ─────────

def learning_loops() -> dict:
    """Estado atual dos loops de aprendizado — dados agregados de TODOS os
    usuários (é assim que a inteligência recalibra em produção)."""
    out: dict = {"calibration": {}, "feedback": [], "metrics": []}
    try:
        from app.negotiator.calibration import compute_calibration

        out["calibration"] = compute_calibration().get("triggers", {})
    except Exception as exc:
        logger.debug("calibration: %s", exc)
    try:
        from app.optimizer.queries import get_feedback_stats

        out["feedback"] = get_feedback_stats() or []
    except Exception as exc:
        logger.debug("feedback: %s", exc)
    out["metrics"] = _rows(
        "SELECT metric_key, dimension, value, samples, metric_date"
        " FROM intelligence_metrics ORDER BY metric_date DESC, metric_key LIMIT 40",
        {},
    )
    return out


__all__ = [
    "accounts", "score_history", "fee_history", "negotiations", "challenges",
    "badges", "chat_history", "context_overrides", "goals", "learning_loops",
]
