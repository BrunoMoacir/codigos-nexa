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

    # ── Safe-to-Spend: fonte ÚNICA, a mesma do /forecast ──────────────
    #
    # Havia um ramo que reescrevia o total como "renda − obrigações − colchão"
    # lendo `income_profile.total_income` — atributo que o IncomeProfile não
    # tem. Era código morto, mas deixava a impressão de dois cálculos. O
    # número é o do projetor: o mínimo do saldo projetado nos próximos 30 dias
    # menos o colchão de segurança, que já desconta as obrigações futuras.
    sts = result["projections"]["safe_to_spend"]
    margem = float(getattr(sts, "safe_to_spend_total", 0.0) or 0.0)
    margem_diaria = float(getattr(sts, "safe_to_spend_daily", 0.0) or 0.0)

    # ── O que já saiu no mês corrente, e de quando é o dado ──────────
    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    spent_to_date = 0.0
    data_as_of = None

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
            if date_col:
                ultima = txns.select(pl.col(date_col).cast(pl.Date).max()).item()
                data_as_of = ultima.isoformat() if ultima else None
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

    # Extrato parado há mais de uma semana: "0% do mês usado" não é zero —
    # é ausência de dado. O widget mostrava "pode gastar com tranquilidade"
    # sobre um extrato de 35 dias atrás.
    stale = True
    if data_as_of:
        stale = (today - date.fromisoformat(data_as_of)).days > _DIAS_PARA_DADO_VELHO

    # ── pct_consumed ──────────────────────────────────────────────────
    # Fatia do dinheiro disponível no mês que já saiu: gasto / (gasto + margem
    # que ainda resta). A margem é LÍQUIDA do que já foi gasto (o saldo
    # projetado parte do saldo atual), então subtrair o gasto dela de novo —
    # como o widget fazia — contava a despesa duas vezes.
    base = spent_to_date + margem
    pct_consumed = round(spent_to_date / base * 100, 2) if base > 0 else 0.0

    return {
        "user_id": user_id,
        "month": today.strftime("%Y-%m"),
        "safe_to_spend_total": round(margem, 2),
        "spent_to_date": round(spent_to_date, 2),
        "pct_consumed": pct_consumed,
        "safe_to_spend_daily": round(margem_diaria, 2),
        "current_balance": round(float(getattr(sts, "current_balance", 0.0) or 0.0), 2),
        "risk_level": getattr(sts, "risk_level", "LOW"),
        "data_as_of": data_as_of,
        "stale": stale,
    }


_DIAS_PARA_DADO_VELHO = 7


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT — WIDGET (R1.d)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _brl_inteiro(valor: float) -> str:
    """R$ 1.234 (pt-BR, sem centavos) — o f-string antigo dava 'R$ 1,234'."""
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


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

    # O mesmo valor diário do /forecast. O widget dividia a margem pelos dias
    # restantes do mês do calendário, o forecast pelos 30 dias do horizonte:
    # a mesma usuária via R$ 368/dia na homescreen e R$ 355/dia no chat.
    daily = round(float(full.get("safe_to_spend_daily", 0.0)), 2)
    margem = round(float(full.get("safe_to_spend_total", 0.0)), 2)
    pct = float(full.get("pct_consumed", 0.0))
    stale = bool(full.get("stale"))
    data_as_of = full.get("data_as_of")

    if margem <= 0 or daily <= 0:
        status_key = "CRITICO"
        # Com margem zero a linha antiga dizia "0% do mês usado · R$ 0
        # restantes" ao lado de "Segure os gastos" — contraditório.
        subline = "Sem margem segura: as obrigações já comprometem o saldo"
    elif pct >= 95:
        status_key, subline = "CRITICO", _WIDGET_STATUS["CRITICO"][1]
    elif pct >= 75 or full.get("risk_level") in ("HIGH", "CRITICAL"):
        status_key, subline = "ATENCAO", _WIDGET_STATUS["ATENCAO"][1]
    else:
        status_key, subline = "OK", _WIDGET_STATUS["OK"][1]

    if stale:
        quando = (
            f"{data_as_of[8:10]}/{data_as_of[5:7]}" if data_as_of else "data desconhecida"
        )
        if status_key == "OK":
            # não dá para afirmar tranquilidade sobre dado velho
            status_key = "ATENCAO"
            subline = f"Extrato de {quando} — sincronize o banco para atualizar"
        else:
            subline = f"{subline} · extrato de {quando}"

    color = _WIDGET_STATUS[status_key][0]
    return {
        "daily": daily,
        "remaining_month": margem,
        "pct_consumed": pct,
        "status": status_key,
        "color": color,
        "headline": f"{_brl_inteiro(daily)}/dia nos próximos 30 dias",
        "subline": subline,
        "data_as_of": data_as_of,
        "stale": stale,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
