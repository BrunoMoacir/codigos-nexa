# app/db/queries/optimizer_queries.py
# Queries PostgreSQL/SQLAlchemy para o módulo Nexa Optimizer (F2)
# Salva e busca relatórios de otimização de cartões.

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy import func

from app.core.database import SessionLocal
from app.optimizer.models_orm import OptimizationReport, RecommendationFeedback

logger = logging.getLogger(__name__)


def save_optimization_report(report: dict) -> None:
    """Persiste um OptimizationReport (dict) no PostgreSQL. Faz upsert por report_id."""
    db = SessionLocal()
    try:
        best_card = report.get("best_card") or {}

        existing = db.query(OptimizationReport).filter(
            OptimizationReport.report_id == report["report_id"]
        ).first()

        if existing:
            # UPDATE
            existing.user_id = report["user_id"]
            existing.generated_at = str(report["generated_at"])
            existing.recommendation_type = report["recommendation_type"]
            existing.best_card_id = best_card.get("card_id")
            existing.best_card_name = best_card.get("card_name")
            existing.net_gain_expected = best_card.get("net_gain_expected")
            existing.net_gain_min = best_card.get("net_gain_min")
            existing.net_gain_max = best_card.get("net_gain_max")
            existing.confidence_score = best_card.get("confidence_score")
            existing.liquidity_impact = best_card.get("liquidity_impact")
            existing.liquidity_risk = best_card.get("liquidity_risk")
            existing.data_sources = json.dumps(report.get("data_sources", []))
            existing.strategy_text = report.get("strategy_text", "")
            existing.warnings = json.dumps(report.get("warnings", []))
            existing.full_report_json = json.dumps(report, default=str)
        else:
            # INSERT
            row = OptimizationReport(
                report_id=report["report_id"],
                user_id=report["user_id"],
                generated_at=str(report["generated_at"]),
                recommendation_type=report["recommendation_type"],
                best_card_id=best_card.get("card_id"),
                best_card_name=best_card.get("card_name"),
                net_gain_expected=best_card.get("net_gain_expected"),
                net_gain_min=best_card.get("net_gain_min"),
                net_gain_max=best_card.get("net_gain_max"),
                confidence_score=best_card.get("confidence_score"),
                liquidity_impact=best_card.get("liquidity_impact"),
                liquidity_risk=best_card.get("liquidity_risk"),
                data_sources=json.dumps(report.get("data_sources", [])),
                strategy_text=report.get("strategy_text", ""),
                warnings=json.dumps(report.get("warnings", [])),
                full_report_json=json.dumps(report, default=str),
            )
            db.add(row)

        db.commit()
        logger.info("Relatório %s salvo para user %s", report['report_id'], report['user_id'])
    except Exception as e:
        db.rollback()
        logger.error("Erro ao salvar relatório: %s", e)
        raise
    finally:
        db.close()


def get_optimization_reports(user_id: str) -> list[dict]:
    """Retorna lista de relatórios resumidos de um usuário (mais recente primeiro)."""
    db = SessionLocal()
    try:
        rows = db.query(OptimizationReport).filter(
            OptimizationReport.user_id == user_id
        ).order_by(OptimizationReport.generated_at.desc()).all()

        return [
            {
                "report_id": r.report_id,
                "user_id": r.user_id,
                "generated_at": r.generated_at,
                "recommendation_type": r.recommendation_type,
                "best_card_id": r.best_card_id,
                "best_card_name": r.best_card_name,
                "net_gain_expected": r.net_gain_expected,
                "net_gain_min": r.net_gain_min,
                "net_gain_max": r.net_gain_max,
                "confidence_score": r.confidence_score,
                "liquidity_impact": r.liquidity_impact,
                "liquidity_risk": r.liquidity_risk,
                "data_sources": r.data_sources,
                "strategy_text": r.strategy_text,
                "warnings": r.warnings,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro ao buscar relatórios de %s: %s", user_id, e)
        return []
    finally:
        db.close()


def get_optimization_report_by_id(report_id: str) -> Optional[dict]:
    """Retorna o relatório completo (full_report_json) pelo report_id."""
    db = SessionLocal()
    try:
        row = db.query(OptimizationReport).filter(
            OptimizationReport.report_id == report_id
        ).first()

        if not row or not row.full_report_json:
            return None

        return json.loads(row.full_report_json)
    except Exception as e:
        logger.error("Erro ao buscar relatório %s: %s", report_id, e)
        return None
    finally:
        db.close()


# ─── Feedback de recomendações ────────────────────────────────────────────────

# Mapa estático: InsightType → detector responsável por gerar o sinal
INSIGHT_DETECTOR: dict[str, str] = {
    "TROCAR_PRIMARIO":   "LifestyleClassifier",
    "PORTFOLIO_MULTI":   "MultiCardStrategist",
    "ATIVAR_BENEFICIO":  "BenefitViabilityFilter",
    "CANCELAR_CARTAO":   "CardSimulator",
    "ATINGIR_ISENCAO":   "CardSimulator",
    "MUDAR_CATEGORIA":   "TrendDetector",
    "SOLICITAR_UPGRADE": "CardKnowledgeBase",
}


def _extract_insight_signals(insight: dict[str, Any]) -> dict[str, Any]:
    """Extrai sinais diretamente do objeto insight salvo no relatório."""
    gain = insight.get("gain_interval") or {}
    return {k: v for k, v in {
        "card_id":                insight.get("card_id"),
        "card_name":              insight.get("card_name"),
        "confidence_score":       insight.get("confidence_score"),
        "gain_expected_monthly":  gain.get("expected"),
        "gain_conservative_monthly": gain.get("conservative"),
        "effort":                 insight.get("effort"),
        "tags":                   insight.get("tags", []),
    }.items() if v is not None}


def find_insight_in_report(report: dict[str, Any], insight_id: str) -> Optional[dict[str, Any]]:
    """Retorna o dict do insight com o dado insight_id, ou None se não encontrado."""
    for insight in report.get("insights", []):
        if insight.get("insight_id") == insight_id:
            return insight
    return None


def save_recommendation_feedback(
    recommendation_id: str,
    user_id: str,
    insight_id: str,
    insight_type: str,
    outcome: str,
    reason: Optional[str],
    insight_data: dict[str, Any],
) -> str:
    """
    Persiste o feedback do usuário sobre um insight específico.

    Sinais são extraídos do próprio dict do insight (não do user_profile_summary),
    garantindo que reflitam os valores exatos usados na geração da recomendação.

    Retorna o feedback_id gerado (UUID).
    """
    feedback_id = str(uuid.uuid4())
    detector = INSIGHT_DETECTOR.get(insight_type, "Unknown")
    signals = _extract_insight_signals(insight_data)

    db = SessionLocal()
    try:
        row = RecommendationFeedback(
            id=feedback_id,
            recommendation_id=recommendation_id,
            insight_id=insight_id,
            user_id=user_id,
            insight_type=insight_type,
            detector=detector,
            signals_json=json.dumps(signals, default=str),
            outcome=outcome,
            reason=reason,
        )
        db.add(row)
        db.commit()
        logger.info(
            "Feedback %s salvo: report=%s insight=%s outcome=%s",
            feedback_id, recommendation_id, insight_type, outcome,
        )
        return feedback_id
    except Exception as e:
        db.rollback()
        logger.error("Erro ao salvar feedback: %s", e)
        raise
    finally:
        db.close()


def get_feedback_stats(
    insight_type: Optional[str] = None,
    detector: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Retorna estatísticas de aceitação agrupadas por (detector, insight_type).

    Usado pelo endpoint GET /optimizer/feedback/stats e pela função
    get_feedback_weights() para alimentar o ranking com pesos aprendidos.
    """
    db = SessionLocal()
    try:
        q = db.query(RecommendationFeedback)
        if insight_type:
            q = q.filter(RecommendationFeedback.insight_type == insight_type)
        if detector:
            q = q.filter(RecommendationFeedback.detector == detector)

        rows = q.all()

        # Agrega em memória — volume esperado é pequeno (< 10k linhas)
        buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"total": 0, "accepted": 0, "ignored": 0, "rejected": 0}
        )
        for r in rows:
            key = (r.detector, r.insight_type)
            buckets[key]["total"] += 1
            buckets[key][r.outcome.lower()] = buckets[key].get(r.outcome.lower(), 0) + 1

        result = []
        for (det, ins), counts in sorted(buckets.items()):
            total = counts["total"]
            accepted = counts.get("accepted", 0)
            result.append({
                "detector": det,
                "insight_type": ins,
                "total": total,
                "accepted": accepted,
                "ignored": counts.get("ignored", 0),
                "rejected": counts.get("rejected", 0),
                "acceptance_rate": round(accepted / total, 4) if total else 0.0,
            })
        return result
    except Exception as e:
        logger.error("Erro ao buscar feedback stats: %s", e)
        return []
    finally:
        db.close()


_GLOBAL_MIN_SAMPLES = 10  # amostras mínimas globais para peso global
_USER_MIN_SAMPLES   = 5   # amostras mínimas do usuário para peso individual
_USER_WEIGHT_MIN    = 0.75
_USER_WEIGHT_MAX    = 1.25


def get_global_feedback_weights() -> dict[str, float]:
    """
    Peso global por insight_type calculado sobre todos os usuários.

    Fórmula: weight = 0.5 + acceptance_rate  → range [0.5, 1.5]
    Floor: ≥ 10 amostras por tipo para evitar overfitting.
    """
    stats = get_feedback_stats()
    weights: dict[str, float] = {}
    for s in stats:
        if s["total"] >= _GLOBAL_MIN_SAMPLES:
            weights[s["insight_type"]] = round(0.5 + s["acceptance_rate"], 4)
    return weights


def get_user_feedback_weights(user_id: str) -> dict[str, float]:
    """
    Peso individual por insight_type calculado sobre o histórico deste usuário.

    Só incluído quando o usuário tem ≥ 5 feedbacks para o tipo.
    Peso clamped em [0.75, 1.25] para não destruir o ranking com poucos dados:
    mesmo aceitação 100% produz 1.25×, não 1.5× — o global já captura isso.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(RecommendationFeedback)
            .filter(RecommendationFeedback.user_id == user_id)
            .all()
        )
    except Exception as e:
        logger.error("Erro ao buscar feedbacks do usuário %s: %s", user_id, e)
        return {}
    finally:
        db.close()

    by_type: dict[str, list] = defaultdict(list)
    for row in rows:
        by_type[row.insight_type].append(row)

    weights: dict[str, float] = {}
    for itype, type_rows in by_type.items():
        if len(type_rows) < _USER_MIN_SAMPLES:
            continue
        total = len(type_rows)
        accepted = sum(1 for r in type_rows if r.outcome.upper() == "ACCEPTED")
        raw = 0.5 + accepted / total
        weights[itype] = round(max(_USER_WEIGHT_MIN, min(_USER_WEIGHT_MAX, raw)), 4)

    return weights


def get_feedback_weights(user_id: str | None = None) -> dict[str, float]:
    """
    Peso final por insight_type = peso_global × peso_usuário.

    peso_global ∈ [0.5, 1.5]    — aprende com todos os usuários (≥ 10 amostras)
    peso_usuário ∈ [0.75, 1.25] — ajusta preferências individuais (≥ 5 amostras)

    Se o usuário não tiver dados suficientes, só o peso global é aplicado.
    Se nenhum dado global disponível para o tipo, retorna 1.0 implícito (ausência de chave).

    Exemplo:
        global TROCAR_PRIMARIO = 1.30  (80% aceitação global)
        user   TROCAR_PRIMARIO = 0.75  (usuário rejeita sempre)
        final                  = 0.975
    """
    global_w = get_global_feedback_weights()
    if user_id is None:
        return global_w

    user_w = get_user_feedback_weights(user_id)
    if not user_w:
        return global_w

    all_types = set(global_w) | set(user_w)
    return {
        itype: round(global_w.get(itype, 1.0) * user_w.get(itype, 1.0), 4)
        for itype in all_types
    }
