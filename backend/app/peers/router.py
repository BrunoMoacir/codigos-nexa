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
from app.core.security import get_current_user

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
async def compare_peers(
    user_id: str,
    monthly_income: float = Query(
        ...,
        gt=0,
        description="Renda mensal líquida (R$). Determina a faixa de renda de referência.",
    ),
    history_months: int = Query(
        default=3,
        ge=1,
        le=12,
        description="Meses de histórico de transações a considerar (padrão: 3).",
    ),
    _: str = Depends(get_current_user),
) -> dict:
    """Compara o perfil de gastos do usuário com benchmarks da faixa de renda."""
    import polars as pl
    import datetime

    logger.info(
        "GET /peers/compare/%s | income=R$%.0f | history=%dm",
        user_id, monthly_income, history_months,
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

    # ── 2. Agregar por categoria e calcular média mensal ──────────────
    raw: dict[str, float] = {}
    for row in debit_rows:
        cat = (row.get("category") or "outros").lower().strip()
        raw[cat] = raw.get(cat, 0.0) + abs(float(row["amount"]))

    category_spending = (
        {k: v / history_months for k, v in raw.items()}
        if history_months > 1
        else raw
    )

    # ── 3. Comparar com benchmarks ────────────────────────────────────
    try:
        report = _comparator.compare(
            monthly_income=monthly_income,
            category_spending=category_spending,
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
