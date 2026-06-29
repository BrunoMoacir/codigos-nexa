"""
app/jobs/opportunity_scan.py — Job diário 03h00 (OPP)

Para cada usuário ativo:
  1. calcula dinheiro parado (avg_income_3m − avg_expenses_3m)
  2. busca CDI via AnbimaConnector (fallback 0.83% a.m.)
  3. determina top_opportunity e top_gain_brl
  4. persiste snapshot em opportunity_snapshots

Lido por: agent/tools/get_opportunities.py (histórico de recomendações)
          agent/tools/get_annual_wrapped.py (V2 Wrapped)
"""

import logging
import uuid
from datetime import date, datetime, timezone, timedelta

from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)

# LCI mínima prática para recomendar produto isento (R$)
_LCI_MIN_AMOUNT = 1_000.0


@job_guard("opportunity_scan")
async def run_opportunity_scan() -> None:
    user_ids = get_active_user_ids()
    logger.info("[opportunity_scan] %d usuários ativos", len(user_ids))

    cdi_monthly = _get_cdi_monthly()
    cdi_annual_decimal = (1 + cdi_monthly) ** 12 - 1

    success = errors = skipped = 0

    for user_id in user_ids:
        try:
            persisted = _scan_user(user_id, cdi_monthly, cdi_annual_decimal)
            if persisted:
                success += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("[opportunity_scan] user=%s erro: %s", user_id, exc)
            errors += 1

    logger.info(
        "[opportunity_scan] done: %d snapshots, %d sem ociosidade, %d erros",
        success, skipped, errors,
    )


# ── Lógica por usuário ────────────────────────────────────────────────

def _scan_user(user_id: str, cdi_monthly: float, cdi_annual: float) -> bool:
    """
    Calcula idle money e persiste snapshot.
    Retorna True se snapshot foi gravado, False se o usuário não tem saldo ocioso.
    """
    from app.core.db.queries import get_transactions_for_user

    df = get_transactions_for_user(user_id)
    if df.is_empty():
        return False

    idle_amount = _calc_idle_amount(df)
    if idle_amount <= 0:
        return False

    monthly_loss = round(idle_amount * cdi_monthly, 2)

    top_opportunity, top_gain_brl = _pick_top_opportunity(
        idle_amount=idle_amount,
        cdi_monthly=cdi_monthly,
    )

    _persist_snapshot(
        user_id=user_id,
        idle_amount=idle_amount,
        monthly_loss=monthly_loss,
        top_opportunity=top_opportunity,
        top_gain_brl=top_gain_brl,
        cdi_at_capture=round(cdi_annual, 4),
    )
    return True


def _calc_idle_amount(df) -> float:
    """Dinheiro parado estimado: avg_income_3m − avg_expenses_3m."""
    try:
        import polars as pl

        date_col = "transaction_date" if "transaction_date" in df.columns else "date"
        today = date.today()
        cutoff = today.replace(day=1)
        for _ in range(3):
            cutoff = (cutoff.replace(day=1) - timedelta(days=1)).replace(day=1)

        df_recent = df.filter(pl.col(date_col) >= cutoff)
        if df_recent.is_empty():
            df_recent = df

        income = df_recent.filter(pl.col("amount") > 0)["amount"].sum()
        expenses_rows = df_recent.filter(pl.col("amount") < 0)
        expenses = expenses_rows["amount"].sum().abs() if expenses_rows.height > 0 else 0.0

        months = max(1, (today.year - cutoff.year) * 12 + today.month - cutoff.month)
        return max(0.0, round(income / months - expenses / months, 2))
    except Exception as exc:
        logger.debug("[opportunity_scan] _calc_idle_amount: %s", exc)
        return 0.0


def _pick_top_opportunity(idle_amount: float, cdi_monthly: float) -> tuple[str, float]:
    """
    Escolhe o produto mais rentável após IR para o saldo ocioso informado.

    Regra simplificada (até o módulo 4.1 ter catálogo completo):
    - >= R$ 1.000 e > 360 dias → LCI/LCA 90% CDI (isento)
      líquido ≈ 0.90 × CDI > CDB líquido (100% CDI − 20% IR = 0.80 × CDI)
    - < R$ 1.000 → CDB liquidez diária (mais acessível)
    """
    if idle_amount >= _LCI_MIN_AMOUNT:
        # LCI 90% CDI, isento: rendimento > CDB 100% CDI após IR
        gain = round(idle_amount * cdi_monthly * 0.90, 2)
        label = "LCI/LCA 90% CDI (isento IR)"
    else:
        # CDB liquidez diária, ~100% CDI, IR 22.5% (curto prazo)
        gain = round(idle_amount * cdi_monthly * 0.775, 2)
        label = "CDB liquidez diária 100% CDI"

    return label, gain


def _get_cdi_monthly() -> float:
    """Taxa CDI mensal via AnbimaConnector; fallback 0.83% a.m. (≈10% a.a.)."""
    try:
        from app.architect.connectors.anbima import AnbimaConnector
        rates = AnbimaConnector().get_rates()
        annual = rates.get("cdi_annual", 0.10)
        return (1 + annual) ** (1 / 12) - 1
    except Exception as exc:
        logger.debug("[opportunity_scan] CDI fallback: %s", exc)
        return 0.0083


def _persist_snapshot(
    user_id: str,
    idle_amount: float,
    monthly_loss: float,
    top_opportunity: str,
    top_gain_brl: float,
    cdi_at_capture: float,
) -> None:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO opportunity_snapshots"
                "   (id, user_id, captured_at, idle_amount, monthly_loss,"
                "    top_opportunity, top_gain_brl, cdi_at_capture)"
                " VALUES (:id, :uid, :ts, :idle, :loss, :top, :gain, :cdi)"
            ),
            {
                "id":   str(uuid.uuid4()),
                "uid":  user_id,
                "ts":   now,
                "idle": idle_amount,
                "loss": monthly_loss,
                "top":  top_opportunity,
                "gain": top_gain_brl,
                "cdi":  cdi_at_capture,
            },
        )
        db.commit()
