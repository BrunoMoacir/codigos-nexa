"""
app/architect/feedback_queries.py - Persistência de feedback e estado de calibração

Responsabilidade:
    Operações de banco para:
      - Gravar feedback pós-simulação (SimulationFeedback)
      - Verificar e disparar o trigger de calibração com SELECT FOR UPDATE
        (evita race condition: dois saves simultâneos não disparam duas calibrações)
      - Listar simulações pendentes de feedback (polling endpoint)
      - Carregar e salvar o CalibrationState (linha única, id=1)
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.architect.models_orm import CalibrationState, SimulationFeedback
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# Mínimo de feedbacks totais para disparar uma rodada de calibração
MIN_FEEDBACKS_FOR_TRIGGER = 20
MIN_DAYS_BETWEEN_CALIBRATIONS = 7


# ─── Feedback ────────────────────────────────────────────────────────────────


def save_feedback_and_check_trigger(
    simulation_id: str,
    user_id: str,
    feedback_request: Any,
    simulation_snapshot: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], bool]:
    """
    Grava o feedback e retorna (feedback_id, should_calibrate).

    should_calibrate=True quando:
      - total de feedbacks ≥ MIN_FEEDBACKS_FOR_TRIGGER
      - AND passaram ≥ MIN_DAYS_BETWEEN_CALIBRATIONS desde a última calibração

    Usa SELECT FOR UPDATE no CalibrationState para garantir que apenas uma
    thread por janela de tempo dispare a calibração (sem celery necessário).

    Args:
        simulation_snapshot: dict extraído do response_json da simulação original.
                             Usado para copiar risk_score/confidence_score/asset_type.
    """
    try:
        with SessionLocal() as db:
            snap = simulation_snapshot or {}
            feedback_id = str(uuid.uuid4())

            fb = SimulationFeedback(
                id=feedback_id,
                simulation_id=simulation_id,
                user_id=user_id,
                feedback_followed=feedback_request.feedback_followed,
                strategy_used=feedback_request.strategy_used.value,
                npv_deviation=feedback_request.npv_deviation,
                rate_deviation=feedback_request.rate_deviation,
                actual_contemplation_month=feedback_request.actual_contemplation_month,
                actual_rate_obtained=feedback_request.actual_rate_obtained,
                risk_score_at_simulation=snap.get("risk_score"),
                risk_profile_at_simulation=snap.get("risk_profile"),
                confidence_score_at_simulation=snap.get("confidence_score"),
                asset_type=snap.get("asset_type", "OUTRO"),
            )
            db.add(fb)
            db.flush()  # grava row sem commit; obtém id, libera sequência

            # Lock exclusivo na linha de estado → serializa o check do trigger
            state = (
                db.query(CalibrationState)
                .with_for_update()
                .filter_by(id=1)
                .first()
            )
            if state is None:
                state = CalibrationState(id=1)
                db.add(state)
                db.flush()

            total = db.query(func.count(SimulationFeedback.id)).scalar() or 0
            now = datetime.now(timezone.utc)
            days_since = (
                (now - state.last_calibrated_at).days
                if state.last_calibrated_at
                else 999
            )

            should_calibrate = (
                total >= MIN_FEEDBACKS_FOR_TRIGGER
                and days_since >= MIN_DAYS_BETWEEN_CALIBRATIONS
            )

            if should_calibrate:
                # Marca ANTES do commit — threads concorrentes que adquirirem o lock
                # em seguida verão last_calibrated_at = now e não entrarão no bloco.
                state.last_calibrated_at = now
                state.calibration_version += 1

            db.commit()
            return feedback_id, should_calibrate

    except Exception as exc:
        logger.warning("feedback_queries.save_feedback_and_check_trigger | erro: %s", exc)
        return None, False


def get_pending_feedback(
    user_id: str,
    window_days: int = 180,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retorna simulações do usuário sem feedback criadas há ≥ window_days dias.

    Usado pelo endpoint GET /architect/simulations/pending-feedback para que o
    frontend exiba o prompt de avaliação na próxima abertura do app.
    """
    try:
        from app.architect.models_orm import ArchitectSimulation

        with SessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

            # IDs de sims que já têm feedback deste usuário
            already_done = {
                row[0]
                for row in db.query(SimulationFeedback.simulation_id)
                .filter(SimulationFeedback.user_id == user_id)
                .all()
            }

            sims = (
                db.query(ArchitectSimulation)
                .filter(
                    ArchitectSimulation.user_id == user_id,
                    ArchitectSimulation.created_at <= cutoff,
                )
                .order_by(ArchitectSimulation.created_at.asc())
                .limit(limit)
                .all()
            )

            result = []
            now = datetime.now(timezone.utc)
            for sim in sims:
                if sim.id in already_done:
                    continue
                months_since = max(
                    0,
                    int((now - sim.created_at).days / 30),
                )
                result.append({
                    "simulation_id": sim.id,
                    "created_at": sim.created_at,
                    "recommended_strategy": sim.recommended_strategy,
                    "target_amount": sim.target_amount,
                    "asset_type": sim.asset_type,
                    "months_since_simulation": months_since,
                })
            return result

    except Exception as exc:
        logger.warning("feedback_queries.get_pending_feedback | erro: %s", exc)
        return []


def get_feedbacks_for_calibration(db) -> List[SimulationFeedback]:
    """Retorna todos os feedbacks disponíveis para uso na calibração."""
    return db.query(SimulationFeedback).all()


def get_consortium_feedbacks_with_p50(db) -> List[Dict[str, Any]]:
    """
    Retorna feedbacks de CONSORTIUM com actual_contemplation_month informado,
    enriquecidos com o P50 simulado (lido do response_json da simulação original).
    """
    from app.architect.models_orm import ArchitectSimulation

    rows = (
        db.query(SimulationFeedback, ArchitectSimulation.response_json)
        .join(
            ArchitectSimulation,
            SimulationFeedback.simulation_id == ArchitectSimulation.id,
            isouter=True,
        )
        .filter(
            SimulationFeedback.strategy_used == "CONSORTIUM",
            SimulationFeedback.actual_contemplation_month.isnot(None),
        )
        .all()
    )

    result = []
    for fb, response_json in rows:
        sim_p50 = None
        if response_json:
            try:
                resp = json.loads(response_json)
                prob = resp.get("consortium_probability") or {}
                sim_p50 = prob.get("expected_months")
            except Exception:
                pass
        result.append({
            "feedback": fb,
            "simulated_p50": sim_p50,
        })
    return result


# ─── Calibration State ───────────────────────────────────────────────────────


def load_calibration_state() -> Optional[Dict[str, Any]]:
    """
    Carrega o estado de calibração do banco.

    Retorna None (não levanta exceção) se a tabela ainda não existir ou
    a linha não tiver sido criada — nesse caso o ArchitectService usa os
    defaults hardcoded.
    """
    try:
        with SessionLocal() as db:
            state = db.query(CalibrationState).filter_by(id=1).first()
            if state is None:
                return None
            return _state_to_dict(state)
    except Exception as exc:
        logger.warning("feedback_queries.load_calibration_state | erro: %s", exc)
        return None


def save_calibration_state(updates: Dict[str, Any]) -> bool:
    """
    Persiste as atualizações no CalibrationState (linha id=1).

    Grava current → previous antes de sobrescrever, permitindo rollback.
    """
    try:
        with SessionLocal() as db:
            state = (
                db.query(CalibrationState)
                .with_for_update()
                .filter_by(id=1)
                .first()
            )
            if state is None:
                state = CalibrationState(id=1)
                db.add(state)

            # Preservar estado anterior para rollback
            if "threshold_conservative" in updates:
                state.previous_threshold_conservative = state.threshold_conservative
                state.threshold_conservative = updates["threshold_conservative"]
            if "threshold_aggressive" in updates:
                state.previous_threshold_aggressive = state.threshold_aggressive
                state.threshold_aggressive = updates["threshold_aggressive"]
            if "bid_params" in updates:
                state.previous_bid_params_json = state.bid_params_json
                state.bid_params_json = json.dumps(updates["bid_params"])
            if "confidence_threshold_upper" in updates:
                state.previous_confidence_threshold_upper = state.confidence_threshold_upper
                state.confidence_threshold_upper = updates["confidence_threshold_upper"]

            if "n_feedbacks_used" in updates:
                state.n_feedbacks_used = updates["n_feedbacks_used"]

            db.commit()
            return True

    except Exception as exc:
        logger.warning("feedback_queries.save_calibration_state | erro: %s", exc)
        return False


def rollback_calibration_state() -> bool:
    """Troca current ↔ previous em todos os campos calibráveis."""
    try:
        with SessionLocal() as db:
            state = (
                db.query(CalibrationState)
                .with_for_update()
                .filter_by(id=1)
                .first()
            )
            if state is None:
                return False

            # Swap conservative threshold
            if state.previous_threshold_conservative is not None:
                state.threshold_conservative, state.previous_threshold_conservative = (
                    state.previous_threshold_conservative,
                    state.threshold_conservative,
                )

            # Swap aggressive threshold
            if state.previous_threshold_aggressive is not None:
                state.threshold_aggressive, state.previous_threshold_aggressive = (
                    state.previous_threshold_aggressive,
                    state.threshold_aggressive,
                )

            # Swap bid params
            if state.previous_bid_params_json is not None:
                state.bid_params_json, state.previous_bid_params_json = (
                    state.previous_bid_params_json,
                    state.bid_params_json,
                )

            # Swap confidence threshold
            if state.previous_confidence_threshold_upper is not None:
                state.confidence_threshold_upper, state.previous_confidence_threshold_upper = (
                    state.previous_confidence_threshold_upper,
                    state.confidence_threshold_upper,
                )

            state.calibration_version += 1
            db.commit()
            return True

    except Exception as exc:
        logger.warning("feedback_queries.rollback_calibration_state | erro: %s", exc)
        return False


# ─── Internal helpers ────────────────────────────────────────────────────────


def _state_to_dict(state: CalibrationState) -> Dict[str, Any]:
    bid_params: Dict[str, Any] = {}
    if state.bid_params_json:
        try:
            bid_params = json.loads(state.bid_params_json)
        except Exception:
            pass

    return {
        "threshold_conservative": state.threshold_conservative,
        "threshold_aggressive": state.threshold_aggressive,
        "bid_params": bid_params,
        "confidence_threshold_upper": state.confidence_threshold_upper,
        "n_feedbacks_used": state.n_feedbacks_used,
        "last_calibrated_at": state.last_calibrated_at,
        "calibration_version": state.calibration_version,
    }
