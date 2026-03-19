# app/api/v1/routes/health_score.py
# MX.1 — Score Financeiro com Evolução Temporal

"""
GET /api/v1/health-score/history/{user_id}?months=6

Retorna o histórico mensal do health_score do usuário com:
  - Score atual
  - Tendência (IMPROVING | STABLE | DECLINING)
  - Variação em 30 e 90 dias
  - Série histórica para gráfico de linha

Fluxo:
  1. Busca transações do usuário em transactions_clean
  2. Roda UserProfileAnalyzer para calcular o score atual
  3. Persiste o snapshot no banco (INSERT OR REPLACE por mês)
  4. Lê histórico e computa tendência
  5. Retorna resposta
"""

import asyncio
import logging
from typing import List, Literal, Optional

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.queries import (
    get_health_score_history,
    save_health_score_snapshot,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.etl.profiles import UserProfileAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health-score", tags=["Health Score (MX.1)"])

TrendType = Literal["IMPROVING", "STABLE", "DECLINING"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HealthScorePoint(BaseModel):
    date: str           # 'YYYY-MM'
    score: int
    savings_rate: Optional[float] = None
    profile_type: Optional[str] = None


class HealthScoreHistoryResponse(BaseModel):
    user_id: str
    current_score: int
    trend: TrendType
    change_30d: Optional[int] = None    # diferença vs mês anterior (null se não há histórico)
    change_90d: Optional[int] = None    # diferença vs 3 meses atrás
    history: List[HealthScorePoint]
    data_quality: str                   # "OK" | "INSUFFICIENT_DATA" | "NO_TRANSACTIONS"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_trend(history: list[dict]) -> TrendType:
    """
    Determina a tendência com base nos últimos 3 meses do histórico.

    Regras:
      - IMPROVING: score subiu ≥ 3 pts vs 3 meses atrás
      - DECLINING: score caiu ≥ 3 pts vs 3 meses atrás
      - STABLE: variação < 3 pts (ruído esperado)
    """
    if len(history) < 2:
        return "STABLE"

    current = history[-1]["health_score"]
    # Compara com o registro mais antigo disponível (até 3 atrás)
    comparison_index = max(0, len(history) - 3)
    reference = history[comparison_index]["health_score"]

    delta = current - reference
    if delta >= 3:
        return "IMPROVING"
    if delta <= -3:
        return "DECLINING"
    return "STABLE"


def _get_change(history: list[dict], months_back: int) -> Optional[int]:
    """Retorna a diferença de score vs N meses atrás. None se não há dados suficientes."""
    if len(history) < months_back + 1:
        return None
    current = history[-1]["health_score"]
    reference = history[-(months_back + 1)]["health_score"]
    return current - reference


def _fetch_transactions_sync(db: Session, user_id: str) -> pl.DataFrame:
    from app.models.transaction import Transaction
    import polars as pl
    try:
        transactions = db.query(Transaction).filter(Transaction.user_id == user_id).all()
        if not transactions:
            return pl.DataFrame()
            
        return pl.DataFrame([
            {
                "transaction_id": tx.transaction_id,
                "user_id": tx.user_id,
                "account_id": tx.account_id,
                "description": tx.description,
                "amount": tx.amount,
                "date": tx.date,
                "transaction_type": tx.transaction_type,
                "category": tx.category,
                "is_recurring": tx.is_recurring,
                "is_installment": tx.is_installment,
                "context_type": tx.context_type,
                "context_confidence": tx.context_confidence,
                "context_override_by_user": tx.context_override_by_user,
                "pj_subcategory": tx.pj_subcategory
            } for tx in transactions
        ])
    except Exception as e:
        logger.error(f"[health-score] Erro ao buscar transações: {e}")
        return pl.DataFrame()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/history/{user_id}", response_model=HealthScoreHistoryResponse)
def get_health_score_history_endpoint(
    user_id: str,
    months: int = Query(default=6, ge=1, le=24, description="Meses de histórico"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
) -> HealthScoreHistoryResponse:
    """
    Retorna o histórico do score de saúde financeira do usuário.

    - Calcula e persiste o snapshot do mês corrente
    - Retorna tendência: IMPROVING | STABLE | DECLINING
    - Retorna variações em 30 dias (mês anterior) e 90 dias (3 meses atrás)
    - Retorna série para gráfico de linha

    **Exemplo de resposta:**
    ```json
    {
      "user_id": "user_123",
      "current_score": 72,
      "trend": "IMPROVING",
      "change_30d": 5,
      "change_90d": 12,
      "history": [
        {"date": "2025-12", "score": 60},
        {"date": "2026-01", "score": 67},
        {"date": "2026-02", "score": 72}
      ],
      "data_quality": "OK"
    }
    ```
    """
    logger.info(f"[health-score] Solicitado histórico para user={user_id} months={months}")

    # ── 1. Buscar transações (Direto pela Sessão/Thread do FastAPI) ─
    transactions_df = _fetch_transactions_sync(db, user_id)

    data_quality = "OK"
    current_score: Optional[int] = None
    current_savings_rate = 0.0
    current_profile_type = "GASTADOR"

    if transactions_df.is_empty():
        data_quality = "NO_TRANSACTIONS"
        logger.warning(f"[health-score] Sem transações para user={user_id}")
    else:
        # ── 2. Calcular score atual via UserProfileAnalyzer ─────────
        try:
            # IncomeProfiler: tenta enriquecer o cálculo com renda filtrada
            income_profile = None
            try:
                from app.etl.income_profiler import IncomeProfiler
                profiler = IncomeProfiler()
                income_profile = profiler.build(transactions_df)
            except Exception as ip_err:
                logger.debug(f"[health-score] IncomeProfiler indisponível: {ip_err}")

            analyzer = UserProfileAnalyzer()
            profile = analyzer.analyze(transactions_df, income_profile=income_profile)

            current_score = profile.financial_health_score
            current_savings_rate = profile.savings_rate
            current_profile_type = profile.profile_type

            if transactions_df.height < 10:
                data_quality = "INSUFFICIENT_DATA"

        except Exception as e:
            logger.error(f"[health-score] Erro ao calcular profile: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Erro ao calcular score financeiro.")

        # ── 3. Persistir snapshot do mês corrente ──────────────────
        saved = save_health_score_snapshot(
            db=db,
            user_id=user_id,
            health_score=current_score,
            savings_rate=current_savings_rate,
            profile_type=current_profile_type,
        )
        if not saved:
            logger.warning(f"[health-score] Snapshot não persistido para user={user_id}")

    # ── 4. Ler histórico ────────────────────────────────────────────
    raw_history = get_health_score_history(db=db, user_id=user_id, months=months)

    history_points = [
        HealthScorePoint(
            date=row["date"],
            score=row["health_score"],
            savings_rate=row.get("savings_rate"),
            profile_type=row.get("profile_type"),
        )
        for row in raw_history
    ]

    # ── 5. Score atual: calculado agora ou último do histórico ──────
    # Quando NO_TRANSACTIONS, não calculamos um novo score — usamos o
    # último snapshot salvo para não poluir o histórico com score=0.
    if current_score is None:
        current_score = raw_history[-1]["health_score"] if raw_history else 0

    # ── 6. Calcular tendência e variações ───────────────────────────
    trend = _compute_trend(raw_history)
    change_30d = _get_change(raw_history, months_back=1)
    change_90d = _get_change(raw_history, months_back=3)

    return HealthScoreHistoryResponse(
        user_id=user_id,
        current_score=current_score,
        trend=trend,
        change_30d=change_30d,
        change_90d=change_90d,
        history=history_points,
        data_quality=data_quality,
    )
