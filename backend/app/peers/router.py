"""
app/api/v1/routes/peers.py — Comparação Anônima com Perfis Similares (MX.4)

Endpoint: GET /peers/compare/{user_id}?monthly_income=8000

Compara o perfil de gastos do usuário com benchmarks agregados da POF/IBGE
por faixa de renda, retornando posicionamento por categoria e percentil de poupança.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status, Depends
from app.core.security import require_owner
from app.core.cache import cache_response

from app.core.db.queries import get_transactions_for_user
from app.peers.peer_comparison import PeerComparator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peers", tags=["Peers — MX.4"])

_comparator = PeerComparator()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /peers/compare/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/compare/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="MX.4 — Comparação com Perfis Similares (IBGE/POF)",
    description=(
        "Compara o perfil de gastos do usuário com benchmarks da Pesquisa de "
        "Orçamentos Familiares (POF/IBGE) para sua faixa de renda. Retorna "
        "posicionamento por categoria ('acima', 'na_media', 'abaixo') e "
        "percentil estimado de poupança vs. perfis similares."
    ),
)
@cache_response(prefix="peers", ttl=1800)  # 30 min
async def compare_peers(
    user_id: str = Depends(require_owner),
    monthly_income: float | None = Query(
        default=None,
        description="Renda mensal líquida (R$). Determina a faixa de renda de referência. Se ausente, estima a partir das transações.",
    ),
    history_months: int = Query(
        default=3,
        ge=1,
        le=12,
        description="Meses de histórico de transações a considerar (padrão: 3).",
    ),
) -> dict:
    """Compara o perfil de gastos do usuário com benchmarks da faixa de renda."""

    import polars as pl
    import datetime

    logger.info(
        "GET /peers/compare/%s | income=%s | history=%dm",
        user_id, str(monthly_income) if monthly_income is not None else "<estimating>", history_months,
    )

    # ── 1. Buscar transações do PostgreSQL ─────────────────────────────
    try:
        df = get_transactions_for_user(user_id)
    except Exception as exc:
        logger.error("Erro ao buscar transações para peers/compare/%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acessar dados de transações.",
        )

    if df.is_empty():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma transação encontrada para user_id='{user_id}'.",
        )

    # ── 1.5 Estimar renda a partir das transações se não fornecida ───
    if monthly_income is None or monthly_income <= 0:
        try:
            from app.forecast.etl.income_profiler import IncomeProfiler

            income_profile = IncomeProfiler().build(df)
            est = getattr(income_profile, "monthly_net_income", None)
            conf = getattr(income_profile, "confidence", 0.0)
            if est and est > 0:
                monthly_income = est
                logger.info("Peers: estimated monthly_income=R$%.0f (confidence=%.2f)", monthly_income, conf)
        except Exception as ie:
            logger.debug("Peers: não foi possível estimar renda: %s", ie)

    if monthly_income is None or monthly_income <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parâmetro 'monthly_income' ausente e não foi possível estimar a partir das transações. Informe 'monthly_income' na query.",
        )

    # ── 2. Detectar cluster comportamental ───────────────────────────
    lifestyle_cluster = "NAO_CLASSIFICADO"
    try:
        from app.optimizer.profiler import ConsumptionProfiler

        prof_df = df
        if "transaction_date" in df.columns and "date" not in df.columns:
            prof_df = df.rename({"transaction_date": "date"})

        beh_profile = ConsumptionProfiler().build(prof_df)
        lifestyle_cluster = beh_profile.lifestyle_cluster
        logger.info(
            "GET /peers/compare/%s | cluster=%s",
            user_id, lifestyle_cluster,
        )
    except Exception as exc:
        logger.debug("Peers: ConsumptionProfiler indisponível para %s: %s", user_id, exc)

    # Filtrar pela janela de meses e apenas débitos
    if "date" in df.columns:
        cutoff = datetime.date.today() - datetime.timedelta(days=history_months * 30)
        df = df.filter(pl.col("date").cast(pl.Date) >= cutoff)

    debit_rows = df.filter(pl.col("amount") < 0).select(["amount", "category"]).to_dicts()

    if not debit_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma transação de débito encontrada para user_id='{user_id}'.",
        )

    # ── 3. Agregar por categoria e calcular média mensal ──────────────
    raw: dict[str, float] = {}
    for row in debit_rows:
        cat = (row.get("category") or "outros").lower().strip()
        raw[cat] = raw.get(cat, 0.0) + abs(float(row["amount"]))

    category_spending = (
        {k: v / history_months for k, v in raw.items()}
        if history_months > 1
        else raw
    )

    # ── 4. Comparar com benchmarks ────────────────────────────────────
    try:
        report = _comparator.compare(
            monthly_income=monthly_income,
            category_spending=category_spending,
            lifestyle_cluster=lifestyle_cluster,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("PeerComparator falhou para %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao calcular comparação com pares.",
        )

    logger.info(
        "GET /peers/compare/%s | faixa=%s | poupanca=%.1f%% | percentil=%s",
        user_id,
        report.income_bracket,
        report.user_savings_rate * 100,
        report.savings_percentile_label,
    )
    return report.to_dict()
