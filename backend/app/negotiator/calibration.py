"""
app/negotiator/calibration.py — Loop fechado do Negociador (F13).

O detector estima `potential_gain` por heurística. Usuários reportam o
DESFECHO real (PATCH /negotiator/history/{id}: sucesso/parcial/recusado +
result_gain). Este módulo fecha o ciclo:

  negotiation_history (desfechos reais)
      → compute_calibration()  [job diário intelligence_metrics]
      → data/negotiator_calibration.json  {trigger_type: fator}
      → get_calibration_factor()  [router do negociador]
      → ganho apresentado = potencial × fator, com a origem declarada
        ("calibrado por N negociações reais")

Regras de honestidade:
  - Fator só existe com ≥ MIN_SAMPLES desfechos resolvidos do trigger;
  - "recusado" conta como realização 0 (não é filtrado — o fator reflete
    a taxa real de sucesso, não só os vencedores);
  - Fator limitado a [0.2, 1.2] — proteção contra outliers/dados sujos;
  - Sem arquivo/amostras → o potencial heurístico segue sozinho (fallback).
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CALIBRATION_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "negotiator_calibration.json"
)
MIN_SAMPLES = 5
_FACTOR_BOUNDS = (0.2, 1.2)
_CACHE_TTL = 10 * 60

_cache: dict = {"loaded_at": 0.0, "mtime": 0.0, "data": None}


def compute_calibration() -> dict:
    """
    Lê negotiation_history e calcula, por trigger_type:
      samples, success_rate, realization_factor (mediana de result/potential).
    Retorna o dicionário completo (o job persiste em CALIBRATION_PATH).
    """
    from sqlalchemy import text

    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            rows = db.execute(text(
                "SELECT trigger_type, result_status, potential_gain, result_gain"
                " FROM negotiation_history"
                " WHERE result_status IN ('sucesso', 'parcial', 'recusado')"
                "   AND potential_gain IS NOT NULL AND potential_gain > 0"
            )).fetchall()
    except Exception as exc:
        logger.warning("[NegotiatorCalibration] leitura falhou: %s", exc)
        return {"triggers": {}, "computed_at": None}

    by_trigger: dict[str, list[float]] = {}
    successes: dict[str, int] = {}
    for trigger, status, potential, result in rows:
        realized = float(result or 0.0) if status != "recusado" else 0.0
        ratio = max(min(realized / float(potential), 3.0), 0.0)
        by_trigger.setdefault(trigger, []).append(ratio)
        if status in ("sucesso", "parcial"):
            successes[trigger] = successes.get(trigger, 0) + 1

    triggers = {}
    for trigger, ratios in by_trigger.items():
        if len(ratios) < MIN_SAMPLES:
            continue
        factor = max(min(statistics.median(ratios), _FACTOR_BOUNDS[1]), _FACTOR_BOUNDS[0])
        triggers[trigger] = {
            "factor": round(factor, 3),
            "samples": len(ratios),
            "success_rate": round(successes.get(trigger, 0) / len(ratios), 3),
        }

    from datetime import datetime, timezone

    return {
        "triggers": triggers,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": MIN_SAMPLES,
    }


def _load() -> dict | None:
    now = time.monotonic()
    if _cache["data"] is not None and (now - _cache["loaded_at"]) < _CACHE_TTL:
        return _cache["data"]
    _cache["loaded_at"] = now
    try:
        if not CALIBRATION_PATH.exists():
            _cache["data"] = None
            return None
        mtime = CALIBRATION_PATH.stat().st_mtime
        if _cache["data"] is not None and mtime == _cache["mtime"]:
            return _cache["data"]
        _cache["data"] = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        _cache["mtime"] = mtime
        return _cache["data"]
    except Exception as exc:
        logger.warning("[NegotiatorCalibration] load falhou: %s", exc)
        _cache["data"] = None
        return None


def get_calibration_factor(trigger_type: str) -> tuple[float, int] | None:
    """(fator, n_amostras) para o trigger, ou None sem dados suficientes."""
    data = _load()
    if not data:
        return None
    entry = (data.get("triggers") or {}).get(trigger_type)
    if not entry:
        return None
    return float(entry["factor"]), int(entry["samples"])


__all__ = ["compute_calibration", "get_calibration_factor", "CALIBRATION_PATH", "MIN_SAMPLES"]
