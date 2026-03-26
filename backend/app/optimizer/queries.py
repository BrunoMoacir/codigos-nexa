# app/db/queries/optimizer_queries.py
# Queries PostgreSQL/SQLAlchemy para o módulo Nexa Optimizer (F2)
# Salva e busca relatórios de otimização de cartões.

from __future__ import annotations

import json
import logging
from typing import Optional

from app.core.database import SessionLocal
from app.optimizer.models_orm import OptimizationReport

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
        logger.info(f"Relatório {report['report_id']} salvo para user {report['user_id']}")
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao salvar relatório: {e}")
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
        logger.error(f"Erro ao buscar relatórios de {user_id}: {e}")
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
        logger.error(f"Erro ao buscar relatório {report_id}: {e}")
        return None
    finally:
        db.close()
