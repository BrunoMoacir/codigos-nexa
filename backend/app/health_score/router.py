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

import json
import logging
from datetime import datetime
from typing import List, Literal, Optional

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.db.queries import (
    get_health_score_history,
    save_health_score_snapshot,
    get_transactions_for_user,
)
from app.core.database import get_db
from app.core.security import require_owner
from app.core.cache import cache_response
from app.forecast.etl.profiles import UserProfileAnalyzer

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
    resilience_score: Optional[int] = None    # sub-score do UserProfileAnalyzer (0–100)
    fss_score: Optional[float] = None         # Financial Stress Score do FSSCalculator (0–100, 100 = máximo estresse)
    fss_level: Optional[str] = None           # SAUDAVEL | ATENCAO | ALERTA | CRITICO
    fss_signals: Optional[List[str]] = None   # sinais que compõem o FSS (ex: "overdraft_usage=12%")


class BadgeResponse(BaseModel):
    badge_type: str
    earned_at: datetime
    metadata: Optional[dict] = None


class BadgesListResponse(BaseModel):
    user_id: str
    badges: List[BadgeResponse]
    total: int


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


def _fetch_transactions_sync(user_id: str, db: Session = None) -> pl.DataFrame:
    """Wrapper testável sobre get_transactions_for_user."""
    return get_transactions_for_user(user_id, db=db)



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/history/{user_id}", response_model=HealthScoreHistoryResponse)
@cache_response(prefix="health_score", ttl=1800)  # 30 min
def get_health_score_history_endpoint(
    user_id: str = Depends(require_owner),
    months: int = Query(default=6, ge=1, le=24, description="Meses de histórico"),
    db: Session = Depends(get_db),
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
    logger.info("[health-score] Solicitado histórico para user=%s months=%d", user_id, months)

    # ── 1. Buscar transações ────────────────────────────────────────────
    transactions_df = _fetch_transactions_sync(user_id, db=db)

    data_quality = "OK"
    current_score: Optional[int] = None
    current_savings_rate = 0.0
    current_profile_type = "GASTADOR"
    current_resilience_score: Optional[int] = None
    current_fss_score: Optional[float] = None
    current_fss_level: Optional[str] = None
    current_fss_signals: Optional[List[str]] = None

    if transactions_df.is_empty():
        data_quality = "NO_TRANSACTIONS"
        logger.warning("[health-score] Sem transações para user=%s", user_id)
    else:
        # ── 2. Calcular score atual via UserProfileAnalyzer ─────────
        try:
            # IncomeProfiler: tenta enriquecer o cálculo com renda filtrada
            income_profile = None
            try:
                from app.forecast.etl.income_profiler import IncomeProfiler
                profiler = IncomeProfiler()
                income_profile = profiler.build(transactions_df)
            except Exception as ip_err:
                logger.debug("[health-score] IncomeProfiler indisponível: %s", ip_err)

            analyzer = UserProfileAnalyzer()
            profile = analyzer.analyze(transactions_df, income_profile=income_profile)

            resilience_score = profile.resilience_score
            current_savings_rate = profile.savings_rate
            current_profile_type = profile.profile_type
            current_resilience_score = resilience_score

            if transactions_df.height < 10:
                data_quality = "INSUFFICIENT_DATA"

        except Exception as e:
            logger.error("[health-score] Erro ao calcular profile: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Erro ao calcular score financeiro.")

        # ── 2b. FSS via ConsumptionProfiler (sinais exclusivos: rotativo, cheque especial, queda de renda)
        fss_value = 0.0
        try:
            from app.optimizer.profiler import ConsumptionProfiler

            prof_df = transactions_df
            if "transaction_date" in transactions_df.columns and "date" not in transactions_df.columns:
                prof_df = transactions_df.rename({"transaction_date": "date"})

            beh_profile = ConsumptionProfiler().build(prof_df)
            fss_value = beh_profile.fss
            current_fss_score  = fss_value
            current_fss_level  = beh_profile.fss_level
            current_fss_signals = getattr(beh_profile, "fss_signals", None)
            logger.info(
                "[health-score] FSS calculado para user=%s: %.1f (%s)",
                user_id, fss_value, beh_profile.fss_level,
            )
        except Exception as fss_err:
            logger.debug("[health-score] ConsumptionProfiler/FSS indisponível: %s", fss_err)

        # ── 2c. Score combinado: resilience (robustez) + FSS invertido (ausência de estresse)
        # Pesos 60/40: resilience é mais abrangente (6 fatores vs 3 exclusivos do FSS).
        current_score = round(resilience_score * 0.60 + (100 - fss_value) * 0.40)
        logger.info(
            "[health-score] Score combinado user=%s: resilience=%d fss=%.1f → combined=%d",
            user_id, resilience_score, fss_value, current_score,
        )

        # ── 3. Persistir snapshot do mês corrente ──────────────────
        saved = save_health_score_snapshot(
            db=db,
            user_id=user_id,
            health_score=current_score,
            savings_rate=current_savings_rate,
            profile_type=current_profile_type,
        )
        if not saved:
            logger.warning("[health-score] Snapshot não persistido para user=%s", user_id)

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

    # ── 4b. Avaliar badges ──────────────────────────────────────────
    if current_score is not None:
        try:
            from app.health_score.badge_service import BadgeService
            BadgeService().evaluate_badges(user_id, current_score, raw_history)
        except Exception as badge_err:
            logger.debug("[health-score] badge evaluation falhou: %s", badge_err)

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
        resilience_score=current_resilience_score,
        fss_score=current_fss_score,
        fss_level=current_fss_level,
        fss_signals=current_fss_signals,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT — BADGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/badges/{user_id}", response_model=BadgesListResponse)
def get_badges_endpoint(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> BadgesListResponse:
    """
    Retorna os badges de gamificação conquistados pelo usuário.

    Badges disponíveis:
      - PRIMEIRO_INSIGHT — primeiro uso do app
      - 3_MESES_VERDE / 6_MESES_VERDE — score >= 70 por N meses consecutivos
      - NEGOCIADOR — gerou ao menos um script de negociação
      - ECONOMIZOU_100 / _500 / _1000 — marcos de economia potencial
    """
    try:
        from sqlalchemy import text

        rows = db.execute(
            text(
                "SELECT badge_type, earned_at, metadata"
                " FROM user_badges"
                " WHERE user_id = :uid"
                " ORDER BY earned_at DESC"
            ),
            {"uid": user_id},
        ).fetchall()

        badges = [
            BadgeResponse(
                badge_type=r[0],
                earned_at=r[1],
                metadata=json.loads(r[2]) if r[2] else None,
            )
            for r in rows
        ]

        return BadgesListResponse(user_id=user_id, badges=badges, total=len(badges))

    except Exception as exc:
        logger.error("[health-score] get_badges user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao buscar badges.")
