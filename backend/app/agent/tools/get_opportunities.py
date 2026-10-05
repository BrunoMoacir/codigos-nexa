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
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

# Ticket OPP1-C — rótulo de confiança por idle_detection_status (mesmo enum do
# OpportunitiesResponse; nenhuma lógica nova aqui, só apresentação).
_STATUS_LABELS = {
    "CONFIRMED": "✅ Confirmado (estável nos últimos 30 dias)",
    "PRELIMINARY": "🔎 Estimativa preliminar — ainda não confirmada",
    "NO_IDLE_MONEY": "✅ Nenhum saldo ocioso além da reserva de emergência",
    "NO_DATA": "❓ Dados insuficientes para estimar",
}


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

    status_label = _STATUS_LABELS.get(result.idle_detection_status, result.idle_detection_status)

    lines = [
        "=== RADAR DE OPORTUNIDADES ===",
        "",
        f"💤 Dinheiro parado estimado: {brl(result.idle_amount)}",
        status_label,
    ]

    if result.idle_amount > 0:
        lines += [
            f"📉 Perda mensal por não investir: {brl(result.monthly_loss_in_checking)}",
            f"📊 CDI atual utilizado: {numero(result.cdi_annual_pct, 2)}% a.a.",
        ]

        top = result.top_opportunity
        if top is not None:
            ir_label = "ISENTO de IR" if top.is_exempt else f"IR {numero(top.ir_rate * 100, 1)}%"
            lines += [
                "",
                "── Melhor opção disponível ──",
                f"• {top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI "
                f"({numero(top.annual_rate_net_pct, 2)}% a.a. líquido) — {ir_label}",
                f"  Rendimento estimado: {brl(top.monthly_gain_brl)}/mês",
            ]
            if top.steps:
                lines += ["", "── Como fazer a troca (passo a passo) ──"]
                lines += [f"{i}. {step}" for i, step in enumerate(top.steps, start=1)]

    lines += ["", result.recommendation]

    savings_section = _build_savings_vs_cdi_section(user_id)
    if savings_section:
        lines += ["", *savings_section]

    last_snapshot = _get_latest_snapshot(user_id)
    if last_snapshot:
        lines += ["", f"📌 Última recomendação salva: {last_snapshot}"]

    from app.opportunities.models import DISCLAIMER
    lines += [
        "",
        "Fonte: CDI via ANBIMA/BCB SGS; SELIC e TR via BCB.",
        DISCLAIMER,
    ]

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────

def _build_savings_vs_cdi_section(user_id: str) -> list[str]:
    """Tickets OPP4-D/E — anexa a comparação poupança vs. CDI quando a
    severidade justifica (>= MEDIUM). Personalizada com o saldo REAL de
    poupança do usuário quando existe (account_balances via sync Pluggy);
    genérica com valor de referência caso contrário — nunca presume saldo.
    Mesmo contrato do endpoint GET /opportunities/savings-vs-cdi."""
    try:
        from app.opportunities.services.savings_vs_cdi import get_savings_vs_cdi_service
        result = get_savings_vs_cdi_service().analyze_for_user(user_id)
    except Exception as exc:
        logger.debug("[Tool] savings_vs_cdi indisponível: %s", exc)
        return []

    if result.status != "BELOW_CDI" or result.severity == "LOW":
        return []

    header = (
        "── Sua poupança vs. CDI (saldo real) ──"
        if result.is_personalized
        else "── Poupança vs. CDI (referência) ──"
    )
    return [
        header,
        f"🐷 Poupança hoje: {numero(result.savings_annual_pct, 2)}% a.a. | CDI: {numero(result.cdi_annual_pct, 2)}% a.a.",
        result.reason,
    ]


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
            gain = f" — ganho estimado {brl(float(row[1]))}" if row[1] else ""
            return f"{row[0]}{gain}"
    except Exception:
        pass
    return None
