# app/api/v1/routes/safe_to_spend.py
"""
GET /api/v1/safe-to-spend/{user_id}

Retorna o orçamento mensal seguro do usuário e o total gasto até hoje.
Alimenta o Safe-to-Spend gauge e a barra de Ritmo de Gastos do frontend.

Campos retornados:
  safe_to_spend_total   → orçamento mensal total disponível (R$)
  spent_to_date         → total de despesas no mês corrente (R$)
  pct_consumed          → percentual do orçamento já consumido
  safe_to_spend_daily   → limite diário calculado pelo backend (R$)
  current_balance       → saldo atual da conta (R$)
  risk_level            → "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  month                 → mês de referência no formato "YYYY-MM"
"""

import logging
from datetime import date

import polars as pl
from fastapi import APIRouter, HTTPException, status, Depends
from app.core.security import require_owner
from app.core.cache import cache_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/safe-to-spend", tags=["Safe-to-Spend"])


@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Safe-to-Spend — Orçamento Mensal e Gasto até Hoje",
    description=(
        "Executa o pipeline financeiro e retorna quanto o usuário pode gastar "
        "com segurança no mês, o total já gasto no mês corrente e o saldo atual. "
        "Fonte: NexaRunner (dados Pluggy mock em dev, Pluggy real em prod)."
    ),
)
@cache_response(prefix="safe_to_spend", ttl=900)
async def get_safe_to_spend(user_id: str = Depends(require_owner)) -> dict:
    """
    Retorna safe-to-spend consolidado com spent_to_date do mês corrente.

    **Exemplo de resposta:**
    ```json
    {
      "user_id": "user_123",
      "month": "2026-03",
      "safe_to_spend_total": 3000.00,
      "spent_to_date": 2401.25,
      "pct_consumed": 80.04,
      "safe_to_spend_daily": 36.00,
      "current_balance": 5000.00,
      "risk_level": "MEDIUM"
    }
    ```
    """
    logger.info("GET /safe-to-spend/%s", user_id)

    try:
        from app.runner import get_runner
        result = get_runner().run_from_db(user_id=user_id, horizon_days=30)
    except Exception as exc:
        logger.error("Erro ao executar pipeline para safe-to-spend/%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar dados financeiros.",
        )

    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline retornou erro: {result.get('error', 'desconhecido')}",
        )

    # ── Safe-to-Spend (SafeToSpendResult dataclass) ──────────────────
    sts = result["projections"]["safe_to_spend"]

    # ── spent_to_date: soma de despesas no mês corrente ───────────────
    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    spent_to_date = 0.0

    try:
        txns: pl.DataFrame = result["transactions"]["pf_pj_classified_df"]
        if not txns.is_empty():
            date_col = next(
                (c for c in ("transaction_date", "date") if c in txns.columns),
                None,
            )
            amount_col = next(
                (c for c in ("amount", "valor") if c in txns.columns),
                None,
            )
            if date_col and amount_col:
                month_expenses = (
                    txns
                    .filter(pl.col(date_col).cast(pl.Date) >= current_month_start)
                    .filter(pl.col(amount_col) < 0)
                    .select(pl.col(amount_col).abs().sum())
                    .item()
                )
                spent_to_date = float(month_expenses or 0.0)
    except Exception as exc:
        logger.warning("Nao foi possivel calcular spent_to_date: %s", exc)
        spent_to_date = 0.0

    # ── pct_consumed ──────────────────────────────────────────────────
    pct_consumed = 0.0
    if sts.safe_to_spend_total > 0:
        pct_consumed = round(spent_to_date / sts.safe_to_spend_total * 100, 2)

    return {
        "user_id": user_id,
        "month": today.strftime("%Y-%m"),
        "safe_to_spend_total": round(sts.safe_to_spend_total, 2),
        "spent_to_date": round(spent_to_date, 2),
        "pct_consumed": pct_consumed,
        "safe_to_spend_daily": round(sts.safe_to_spend_daily, 2),
        "current_balance": round(sts.current_balance, 2),
        "risk_level": sts.risk_level,
    }
