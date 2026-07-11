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
from datetime import date, datetime, timezone

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
    income_profile = result["analysis"].get("income_profile")
    total_income = getattr(income_profile, "total_income", 0.0) if income_profile else 0.0

    # ── Transformar Safe-to-Spend em limite "Mensal" em vez de "Acumulado"
    # O backend projetor olha pro saldo bancário absoluto. Mas o frontend usa o STS como "Orçamento Mensal".
    # Portanto, reescrevemos o "Total Seguro para Gastar" baseando-nos na Renda - Obrigações Fixas Previstas.
    monthly_budget_limit = getattr(sts, "safe_to_spend_total", 0.0)
    if total_income > 0:
        monthly_budget_limit = max(0.0, total_income - abs(sts.total_shadow_invoices) - sts.safety_buffer)

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
    if monthly_budget_limit > 0:
        pct_consumed = round(spent_to_date / monthly_budget_limit * 100, 2)

    return {
        "user_id": user_id,
        "month": today.strftime("%Y-%m"),
        "safe_to_spend_total": round(monthly_budget_limit, 2),
        "spent_to_date": round(spent_to_date, 2),
        "pct_consumed": pct_consumed,
        "safe_to_spend_daily": round(monthly_budget_limit / 30, 2),
        "current_balance": round(sts.current_balance, 2),
        "risk_level": sts.risk_level,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT — WIDGET (R1.d)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Status → cor do widget: verde/amarelo/vermelho (hex para render direto)
_WIDGET_STATUS = {
    "OK":      ("#22c55e", "Pode gastar com tranquilidade"),
    "ATENCAO": ("#eab308", "Gaste com atenção"),
    "CRITICO": ("#ef4444", "Segure os gastos"),
}


@router.get(
    "/{user_id}/widget",
    status_code=status.HTTP_200_OK,
    summary="R1.d — Safe-to-Spend compacto para widget (homescreen/PWA)",
    description=(
        "Payload mínimo do safe-to-spend, desenhado para superfícies de "
        "sistema: widget de homescreen, PWA, watch, extensão. Uma chamada, "
        "~200 bytes, com valor diário, status semafórico, cor pronta e uma "
        "frase de contexto. Reutiliza o cache de 15 min do endpoint completo."
    ),
)
async def get_safe_to_spend_widget(user_id: str = Depends(require_owner)) -> dict:
    """
    **Exemplo de resposta:**
    ```json
    {
      "daily": 86.50,
      "remaining_month": 1730.00,
      "pct_consumed": 42.3,
      "status": "OK",
      "color": "#22c55e",
      "headline": "R$ 86/dia até o fim do mês",
      "subline": "Pode gastar com tranquilidade",
      "updated_at": "2026-07-11T14:02:11Z"
    }
    ```
    """
    logger.info("GET /safe-to-spend/%s/widget", user_id)

    # Reusa o endpoint completo (e o cache Redis dele)
    full = await get_safe_to_spend(user_id=user_id)

    total = float(full.get("safe_to_spend_total", 0.0))
    spent = float(full.get("spent_to_date", 0.0))
    pct = float(full.get("pct_consumed", 0.0))
    remaining = max(0.0, total - spent)

    today = date.today()
    import calendar as _cal
    days_left = max(1, _cal.monthrange(today.year, today.month)[1] - today.day + 1)
    daily = round(remaining / days_left, 2)

    if pct >= 95 or daily <= 0:
        status_key = "CRITICO"
    elif pct >= 75 or full.get("risk_level") in ("HIGH", "CRITICAL"):
        status_key = "ATENCAO"
    else:
        status_key = "OK"

    color, subline = _WIDGET_STATUS[status_key]
    return {
        "daily": daily,
        "remaining_month": round(remaining, 2),
        "pct_consumed": pct,
        "status": status_key,
        "color": color,
        "headline": f"R$ {daily:,.0f}/dia até o fim do mês",
        "subline": subline,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
