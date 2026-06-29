# app/agent/tools/get_opportunities.py
import logging
from datetime import date

from langchain_core.tools import tool

from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)


@tool
def get_opportunities(user_id: str) -> str:
    """
    Detecta dinheiro parado na conta e compara com as melhores opções de investimento.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Tenho dinheiro parado na conta?"
    - "Quanto estou perdendo sem investir?"
    - "Qual o melhor investimento para minha reserva?"
    - "CDB, LCI ou LCA — o que rende mais para mim?"
    - "Meu dinheiro está rendendo na conta?"
    - "Radar de oportunidades de investimento"
    - Qualquer pergunta sobre dinheiro ocioso ou comparação de investimentos.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_opportunities | user=%s", user_id)

    transactions_df = get_transactions_for_user(user_id)

    if transactions_df.is_empty():
        return (
            "Não encontrei histórico de transações para calcular dinheiro parado. "
            "Conecte sua conta bancária via Open Finance para obter essa análise."
        )

    # ── 1. Calcular saldo ocioso (income - expenses, média 3 meses) ──
    idle_amount = _calc_idle_amount(transactions_df)

    if idle_amount <= 0:
        return (
            "Com base no seu histórico recente, seus gastos estão próximos ou acima da sua renda — "
            "não há saldo ocioso identificado no momento. "
            "Reduza gastos variáveis para criar margem de investimento."
        )

    # ── 2. Buscar CDI atual via ANBIMA ───────────────────────────────
    cdi_monthly = _get_cdi_monthly()

    # ── 3. Calcular perda mensal e anual ────────────────────────────
    monthly_loss = idle_amount * cdi_monthly
    annual_loss = idle_amount * ((1 + cdi_monthly) ** 12 - 1)

    # ── 4. Verificar snapshots de oportunidade no histórico ─────────
    top_opportunity = _get_latest_snapshot(user_id)

    lines = [
        "=== RADAR DE OPORTUNIDADES ===",
        "",
        f"💤 Dinheiro parado estimado: R$ {idle_amount:,.2f}",
        f"📉 Perda mensal por não investir: R$ {monthly_loss:,.2f}",
        f"📉 Perda anual estimada: R$ {annual_loss:,.2f}",
        f"📊 CDI atual utilizado: {cdi_monthly * 100:.2f}% a.m.",
        "",
        "── Opções recomendadas ──",
        f"• CDB 100% CDI: R$ {idle_amount * cdi_monthly:,.2f}/mês — tributado (IR regressivo 22,5%→15%)",
        f"• LCI/LCA 90% CDI: R$ {idle_amount * cdi_monthly * 0.90:,.2f}/mês — ISENTO de IR",
        f"  → Breakeven LCI: {(cdi_monthly * 0.775) * 100:.2f}% a.m. já supera CDB líquido após IR",
        "",
        "── Regra prática ──",
        "Para reserva de emergência (até 6x gastos mensais): Tesouro Selic ou CDB com liquidez diária.",
        "Para prazo > 2 anos: LCI/LCA ou CDB longo com alíquota de 15%.",
    ]

    if top_opportunity:
        lines += ["", f"📌 Última recomendação Nexa: {top_opportunity}"]

    lines += [
        "",
        "Fonte: CDI via ANBIMA/BCB SGS. Rentabilidades passadas não garantem futuras.",
    ]

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────

def _calc_idle_amount(df) -> float:
    """Estima dinheiro parado: média de renda menos média de despesas nos últimos 3 meses."""
    try:
        import polars as pl

        date_col = "transaction_date" if "transaction_date" in df.columns else "date"
        today = date.today()
        cutoff = today.replace(day=1)
        # 3 meses atrás
        for _ in range(3):
            cutoff = (cutoff.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)

        df_recent = df.filter(pl.col(date_col) >= cutoff)
        if df_recent.is_empty():
            df_recent = df

        income = df_recent.filter(pl.col("amount") > 0)["amount"].sum()
        expenses = df_recent.filter(pl.col("amount") < 0)["amount"].sum().abs() if \
            df_recent.filter(pl.col("amount") < 0).height > 0 else 0.0

        months = max(1, (today.year - cutoff.year) * 12 + today.month - cutoff.month)
        avg_income = income / months
        avg_expenses = expenses / months
        return max(0.0, round(avg_income - avg_expenses, 2))
    except Exception as exc:
        logger.debug("[get_opportunities] _calc_idle_amount: %s", exc)
        return 0.0


def _get_cdi_monthly() -> float:
    """Retorna CDI mensal via ANBIMA connector; fallback 0.83% a.m. (≈10% a.a.)."""
    try:
        from app.architect.connectors.anbima import AnbimaConnector
        rates = AnbimaConnector().get_rates()
        annual = rates.get("cdi_annual", 0.10)
        return (1 + annual) ** (1 / 12) - 1
    except Exception:
        return 0.0083


def _get_latest_snapshot(user_id: str) -> str | None:
    """Busca última recomendação de oportunidade em opportunity_snapshots."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT top_opportunity, top_gain_brl FROM opportunity_snapshots"
                    " WHERE user_id = :uid ORDER BY captured_at DESC LIMIT 1"
                ),
                {"uid": user_id},
            ).fetchone()
        if row and row[0]:
            gain = f" — ganho estimado R$ {float(row[1]):,.2f}" if row[1] else ""
            return f"{row[0]}{gain}"
    except Exception:
        pass
    return None
