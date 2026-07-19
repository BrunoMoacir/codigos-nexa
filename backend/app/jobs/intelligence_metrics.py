"""
app/jobs/intelligence_metrics.py — Job diário 05h30.

Monitoramento de acurácia da inteligência EM PRODUÇÃO + disparo dos loops
de calibração. É a resposta ao gap "os dados de feedback existem mas nada
os consome": este job transforma as tabelas de desfecho em métricas
persistidas (série temporal) e em artefatos de calibração.

Métricas gravadas em intelligence_metrics (uma linha por dia×métrica×dimensão):
  reco_acceptance_rate / {insight_type}    ← recommendation_feedback (30d)
  negotiation_success_rate / {trigger}     ← negotiation_history (desfechos)
  negotiation_realization_factor / {trigger} ← fator do loop de calibração
  fee_baseline_coverage / open_finance     ← instituições no baseline vivo
  fee_trends_coverage / users_agg          ← bancos no agregado anônimo
  catalog_coverage / open_finance          ← instituições no catálogo OPP
  agent_messages / daily                   ← mensagens de chat nas últimas 24h

Loops disparados:
  - Negociador: compute_calibration() → data/negotiator_calibration.json
    (consumido pelo router do F13 — ganho apresentado vira calibrado).
"""

import json
import logging
from datetime import date, datetime, timezone

from app.jobs._base import job_guard

logger = logging.getLogger(__name__)


@job_guard("intelligence_metrics")
async def run_intelligence_metrics() -> None:
    metrics: list[tuple[str, str, float, int]] = []  # (key, dimension, value, samples)

    metrics += _reco_feedback_metrics()
    negotiation_metrics, calibration = _negotiation_metrics_and_calibration()
    metrics += negotiation_metrics
    metrics += _coverage_metrics()
    metrics += _agent_metrics()

    _persist_calibration(calibration)
    _persist_metrics(metrics)

    logger.info(
        "[intelligence_metrics] %d métricas gravadas | calibração: %d triggers",
        len(metrics), len(calibration.get("triggers", {})),
    )


# ── coletores ────────────────────────────────────────────────────────


def _reco_feedback_metrics() -> list[tuple[str, str, float, int]]:
    """Taxa de aceitação das recomendações por insight_type (últimos 30 dias)."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            rows = db.execute(text(
                "SELECT insight_type,"
                "       COUNT(*) AS total,"
                "       SUM(CASE WHEN UPPER(outcome) = 'ACCEPTED' THEN 1 ELSE 0 END) AS accepted"
                " FROM recommendation_feedback"
                " WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'"
                " GROUP BY insight_type"
            )).fetchall()
        return [
            ("reco_acceptance_rate", str(r[0]), round(int(r[2] or 0) / int(r[1]), 4), int(r[1]))
            for r in rows if int(r[1]) > 0
        ]
    except Exception as exc:
        logger.warning("[intelligence_metrics] reco_feedback: %s", exc)
        return []


def _negotiation_metrics_and_calibration():
    """Sucesso e fator de realização por trigger + artefato de calibração."""
    from app.negotiator.calibration import compute_calibration

    calibration = compute_calibration()
    metrics = []
    for trigger, entry in (calibration.get("triggers") or {}).items():
        metrics.append(
            ("negotiation_success_rate", trigger, entry["success_rate"], entry["samples"])
        )
        metrics.append(
            ("negotiation_realization_factor", trigger, entry["factor"], entry["samples"])
        )
    return metrics, calibration


def _coverage_metrics() -> list[tuple[str, str, float, int]]:
    metrics = []
    # Baseline vivo de tarifas (Open Finance)
    try:
        import app.costs.market_fees_db as fees_module

        if fees_module._LIVE_FEES_PATH.exists():
            data = json.loads(fees_module._LIVE_FEES_PATH.read_text(encoding="utf-8"))
            n = len(data.get("institutions", []))
            metrics.append(("fee_baseline_coverage", "open_finance", float(n), n))
    except Exception as exc:
        logger.debug("[intelligence_metrics] fee_baseline: %s", exc)

    # Agregado anônimo de tarifas dos usuários
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            n = db.execute(text(
                "SELECT COUNT(DISTINCT bank_name) FROM bank_fee_trends"
            )).scalar() or 0
        metrics.append(("fee_trends_coverage", "users_agg", float(n), int(n)))
    except Exception as exc:
        logger.debug("[intelligence_metrics] fee_trends: %s", exc)

    # Catálogo vivo do OPP
    try:
        from pathlib import Path

        catalog = (
            Path(__file__).resolve().parents[1]
            / "opportunities" / "data" / "product_catalog.json"
        )
        if catalog.exists():
            data = json.loads(catalog.read_text(encoding="utf-8"))
            banks = {p.get("bank_name") for p in data.get("products", [])}
            metrics.append(("catalog_coverage", "open_finance", float(len(banks)), len(banks)))
    except Exception as exc:
        logger.debug("[intelligence_metrics] catalog: %s", exc)
    return metrics


def _agent_metrics() -> list[tuple[str, str, float, int]]:
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            n = db.execute(text(
                "SELECT COUNT(*) FROM chat_messages"
                " WHERE role = 'human' AND created_at >= NOW() - INTERVAL '24 hours'"
            )).scalar() or 0
        return [("agent_messages", "daily", float(n), int(n))]
    except Exception as exc:
        logger.debug("[intelligence_metrics] agent: %s", exc)
        return []


# ── persistência ─────────────────────────────────────────────────────


def _persist_calibration(calibration: dict) -> None:
    from app.negotiator.calibration import CALIBRATION_PATH

    try:
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CALIBRATION_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(calibration, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(CALIBRATION_PATH)
    except Exception as exc:
        logger.warning("[intelligence_metrics] persistência de calibração falhou: %s", exc)


def _persist_metrics(metrics: list[tuple[str, str, float, int]]) -> None:
    if not metrics:
        return
    try:
        from app.core.database import SessionLocal
        from app.jobs.models_orm import IntelligenceMetric

        today = date.today()
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for key, dimension, value, samples in metrics:
                db.merge(IntelligenceMetric(
                    metric_date=today,
                    metric_key=key,
                    dimension=dimension,
                    value=value,
                    samples=samples,
                    computed_at=now,
                ))
            db.commit()
    except Exception as exc:
        logger.warning("[intelligence_metrics] persistência de métricas falhou: %s", exc)
