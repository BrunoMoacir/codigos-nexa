# app/agent/tools/get_opportunities.py
"""
Tool do agente ReAct (chat) para o Radar de Oportunidades (OPP).

Delega toda a lógica de dinheiro ocioso e ranking de produtos ao
OpportunityEngine — o mesmo motor usado pelo endpoint REST
(GET /api/v1/opportunities/{user_id}) e pelo job diário. Não duplica
cálculo de idle_amount aqui (ver docs/OPP1_DINHEIRO_PARADO_PLANO.md,
Ticket OPP1-A: antes desta mudança, esta tool tinha uma função
_calc_idle_amount própria que podia divergir do IdleMoneyDetector).

persist_snapshot=False: o chat é consultado sob demanda e não deve gerar
um snapshot em opportunity_snapshots a cada pergunta — persistência fica
a cargo do job diário e do GET explícito da API.
"""
import logging

from langchain_core.tools import tool

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

    from app.opportunities.services.opportunity_engine import OpportunityEngine

    try:
        result = OpportunityEngine().analyze(
            user_id=user_id, holding_months=12, persist_snapshot=False
        )
    except Exception as exc:
        logger.error("[Tool] get_opportunities | user=%s: %s", user_id, exc)
        return (
            "Não consegui calcular o radar de oportunidades agora. "
            "Tente novamente em instantes."
        )

    lines = [
        "=== RADAR DE OPORTUNIDADES ===",
        "",
        f"💤 Dinheiro parado estimado: R$ {result.idle_amount:,.2f}",
    ]

    if result.idle_amount > 0:
        lines += [
            f"📉 Perda mensal por não investir: R$ {result.monthly_loss_in_checking:,.2f}",
            f"📊 CDI atual utilizado: {result.cdi_annual_pct:.2f}% a.a.",
        ]

        top = result.top_opportunity
        if top is not None:
            ir_label = "ISENTO de IR" if top.is_exempt else f"IR {top.ir_rate * 100:.1f}%"
            lines += [
                "",
                "── Melhor opção disponível ──",
                f"• {top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI "
                f"({top.annual_rate_net_pct:.2f}% a.a. líquido) — {ir_label}",
                f"  Rendimento estimado: R$ {top.monthly_gain_brl:,.2f}/mês",
            ]

    lines += ["", result.recommendation]

    last_snapshot = _get_latest_snapshot(user_id)
    if last_snapshot:
        lines += ["", f"📌 Última recomendação salva: {last_snapshot}"]

    lines += [
        "",
        "Fonte: CDI via ANBIMA/BCB SGS. Rentabilidades passadas não garantem futuras.",
    ]

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────

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
