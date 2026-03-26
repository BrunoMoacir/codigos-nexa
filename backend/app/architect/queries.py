"""
app/db/queries/architect_queries.py - Persistência das Simulações F3

Feature: F3 - Nexa Architect
Version: 2.0.0  (migrado de DuckDB para PostgreSQL/SQLAlchemy)

Responsabilidade:
    Todas as operações de banco de dados relacionadas às simulações do
    Nexa Architect (F3). Agora usa SQLAlchemy + PostgreSQL.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import SessionLocal
from app.architect.models_orm import ArchitectSimulation, ArchitectSimulationMetrics

logger = logging.getLogger(__name__)


# ─── Funções Públicas ─────────────────────────────────────────────────────────

def save_simulation(
    user_id: str,
    request: Any,
    response: Any,
    **kwargs,
) -> Optional[str]:
    """
    Persiste uma simulação completa no PostgreSQL via SQLAlchemy.

    Returns:
        UUID da simulação salva (str), ou None em caso de erro.
    """
    simulation_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        request_json = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        response_json = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)

        sim = ArchitectSimulation(
            id=simulation_id,
            user_id=user_id,
            created_at=datetime.now(tz=timezone.utc),
            target_amount=request.target_amount,
            asset_type=request.asset_type.value,
            amortization_type=request.amortization_type.value if hasattr(request, 'amortization_type') and request.amortization_type else None,
            financing_months=request.financing_months,
            down_payment=request.down_payment,
            max_monthly_budget=request.max_monthly_budget,
            recommended_strategy=response.recommended_strategy.value,
            confidence_score=response.confidence_score,
            liquidity_impact=response.liquidity_impact,
            months_to_achieve=response.months_to_achieve,
            expected_cost=response.costs.expected_cost if hasattr(response, 'costs') and response.costs else None,
            request_json=request_json,
            response_json=response_json,
        )
        db.add(sim)
        db.commit()

        logger.info(
            "save_simulation | id=%s user=%s strategy=%s confidence=%.2f",
            simulation_id, user_id,
            response.recommended_strategy.value, response.confidence_score,
        )

        _update_simulation_metrics_internal(db, user_id)
        return simulation_id

    except Exception as exc:
        db.rollback()
        logger.error("save_simulation | ERRO user=%s: %s", user_id, exc, exc_info=True)
        return None
    finally:
        db.close()


def get_simulation(simulation_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Recupera uma simulação pelo seu ID único."""
    db = SessionLocal()
    try:
        row = db.query(ArchitectSimulation).filter(ArchitectSimulation.id == simulation_id).first()
        if row is None:
            return None

        return {
            "id": row.id,
            "user_id": row.user_id,
            "created_at": str(row.created_at) if row.created_at else None,
            "target_amount": row.target_amount,
            "asset_type": row.asset_type,
            "amortization_type": row.amortization_type,
            "financing_months": row.financing_months,
            "down_payment": row.down_payment,
            "max_monthly_budget": row.max_monthly_budget,
            "recommended_strategy": row.recommended_strategy,
            "confidence_score": row.confidence_score,
            "liquidity_impact": row.liquidity_impact,
            "months_to_achieve": row.months_to_achieve,
            "expected_cost": row.expected_cost,
            "request": json.loads(row.request_json) if row.request_json else {},
            "response": json.loads(row.response_json) if row.response_json else {},
        }
    except Exception as exc:
        logger.error("get_simulation | id=%s | ERRO: %s", simulation_id, exc)
        return None
    finally:
        db.close()


def get_user_simulations(
    user_id: str,
    limit: int = 10,
    asset_type: Optional[str] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Lista as últimas simulações de um usuário."""
    db = SessionLocal()
    try:
        query = db.query(ArchitectSimulation).filter(ArchitectSimulation.user_id == user_id)

        if asset_type:
            query = query.filter(ArchitectSimulation.asset_type == asset_type.upper())

        rows = query.order_by(ArchitectSimulation.created_at.desc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "created_at": str(r.created_at) if r.created_at else None,
                "target_amount": r.target_amount,
                "asset_type": r.asset_type,
                "recommended_strategy": r.recommended_strategy,
                "confidence_score": r.confidence_score,
                "liquidity_impact": r.liquidity_impact,
                "months_to_achieve": r.months_to_achieve,
                "expected_cost": r.expected_cost,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.error("get_user_simulations | user=%s | ERRO: %s", user_id, exc)
        return []
    finally:
        db.close()


def get_user_latest_simulation(user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Retorna a simulação mais recente de um usuário."""
    db = SessionLocal()
    try:
        row = db.query(ArchitectSimulation).filter(
            ArchitectSimulation.user_id == user_id
        ).order_by(ArchitectSimulation.created_at.desc()).first()

        if row is None:
            return None

        return get_simulation(row.id)
    except Exception as exc:
        logger.error("get_user_latest_simulation | user=%s | ERRO: %s", user_id, exc)
        return None
    finally:
        db.close()


def update_simulation_metrics(user_id: str, **kwargs) -> bool:
    """Recalcula e persiste as métricas agregadas do usuário."""
    db = SessionLocal()
    try:
        return _update_simulation_metrics_internal(db, user_id)
    except Exception as exc:
        logger.error("update_simulation_metrics | user=%s | ERRO: %s", user_id, exc)
        return False
    finally:
        db.close()


def get_user_metrics(user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Retorna as métricas agregadas de um usuário."""
    db = SessionLocal()
    try:
        row = db.query(ArchitectSimulationMetrics).filter(
            ArchitectSimulationMetrics.user_id == user_id
        ).first()

        if row is None:
            return None

        return {
            "user_id": row.user_id,
            "total_simulations": row.total_simulations,
            "last_simulated_at": str(row.last_simulated_at) if row.last_simulated_at else None,
            "favorite_strategy": row.favorite_strategy,
            "avg_confidence_score": row.avg_confidence_score,
            "first_simulated_at": str(row.first_simulated_at) if row.first_simulated_at else None,
        }
    except Exception as exc:
        logger.error("get_user_metrics | user=%s | ERRO: %s", user_id, exc)
        return None
    finally:
        db.close()


# ─── Helper de Métricas (Interno) ────────────────────────────────────────────

def _update_simulation_metrics_internal(db, user_id: str) -> bool:
    """Recalcula e faz UPSERT nas métricas do usuário."""
    from sqlalchemy import func

    try:
        # Calcular métricas via SQLAlchemy
        metrics = db.query(
            func.count(ArchitectSimulation.id).label("total"),
            func.max(ArchitectSimulation.created_at).label("last_at"),
            func.min(ArchitectSimulation.created_at).label("first_at"),
            func.avg(ArchitectSimulation.confidence_score).label("avg_conf"),
        ).filter(
            ArchitectSimulation.user_id == user_id
        ).first()

        if not metrics or metrics.total == 0:
            return False

        # Estratégia favorita
        fav = db.query(
            ArchitectSimulation.recommended_strategy,
            func.count(ArchitectSimulation.id).label("cnt"),
        ).filter(
            ArchitectSimulation.user_id == user_id
        ).group_by(
            ArchitectSimulation.recommended_strategy
        ).order_by(func.count(ArchitectSimulation.id).desc()).first()

        favorite_strategy = fav.recommended_strategy if fav else None

        # UPSERT — merge do SQLAlchemy
        existing = db.query(ArchitectSimulationMetrics).filter(
            ArchitectSimulationMetrics.user_id == user_id
        ).first()

        if existing:
            existing.total_simulations = metrics.total
            existing.last_simulated_at = metrics.last_at
            existing.first_simulated_at = metrics.first_at
            existing.avg_confidence_score = round(metrics.avg_conf, 4) if metrics.avg_conf else None
            existing.favorite_strategy = favorite_strategy
        else:
            new_metrics = ArchitectSimulationMetrics(
                user_id=user_id,
                total_simulations=metrics.total,
                last_simulated_at=metrics.last_at,
                first_simulated_at=metrics.first_at,
                avg_confidence_score=round(metrics.avg_conf, 4) if metrics.avg_conf else None,
                favorite_strategy=favorite_strategy,
            )
            db.add(new_metrics)

        db.commit()

        logger.debug("_update_metrics | user=%s total=%d favorite=%s", user_id, metrics.total, favorite_strategy)
        return True

    except Exception as exc:
        db.rollback()
        logger.error("_update_metrics | ERRO: %s", exc)
        return False


# ─── Exports ──────────────────────────────────────────────────────────────────

__all__ = [
    "save_simulation",
    "get_simulation",
    "get_user_simulations",
    "get_user_latest_simulation",
    "update_simulation_metrics",
    "get_user_metrics",
]
