# app/agent/tools/get_best_bank.py
"""
Tool do agente ReAct (chat) para o Bank Match — "qual é o melhor banco para mim?".

Delega ao BankMatchService: score composto por banco (rendimento líquido
ajustado a risco + tarifas típicas + cartões do emissor + fit com o perfil
financeiro), com pesos ajustados ao FSS e ao tipo de investidor do usuário.
Mesmo motor do endpoint GET /opportunities/{user_id}/bank-match — nenhum
cálculo duplicado aqui.
"""
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Singletons de módulo — cache dos conectores é por instância (ver OPP4-C).
_bank_match_service = None


def _get_service():
    global _bank_match_service
    if _bank_match_service is None:
        from app.opportunities.services.bank_match import BankMatchService
        _bank_match_service = BankMatchService()
    return _bank_match_service


@tool
def get_best_bank(user_id: str, amount: float = 0.0) -> str:
    """
    Recomenda o melhor banco para o usuário com base no perfil financeiro completo.

    Use esta ferramenta SEMPRE que o usuário perguntar:
    - "Qual o melhor banco para mim?"
    - "Vale a pena trocar de banco?"
    - "Meu banco é bom? Devo mudar?"
    - "Qual banco rende mais / cobra menos / tem melhor cartão?"
    - "Onde devo abrir conta?"
    - Qualquer comparação geral entre bancos (não só investimento).

    Pondera rendimento, tarifas, cartões e o momento financeiro do usuário.
    Para comparar apenas produtos de investimento, use get_opportunities.

    Args:
        user_id: ID do usuário (obrigatório).
        amount: Valor de referência em R$ (opcional; 0 usa o dinheiro ocioso detectado).
    """
    logger.info("[Tool] get_best_bank | user=%s amount=%s", user_id, amount)

    try:
        from app.opportunities.services.opportunity_engine import OpportunityEngine

        transactions_df = OpportunityEngine._fetch_transactions(user_id)
        user_profile = OpportunityEngine._build_user_profile(transactions_df)

        simulated = amount
        if simulated <= 0:
            idle = OpportunityEngine().analyze(
                user_id=user_id, holding_months=12, persist_snapshot=False
            )
            simulated = max(idle.idle_amount, 1_000.0)

        result = _get_service().build(
            user_id=user_id,
            amount=simulated,
            holding_months=12,
            cdi_annual=OpportunityEngine._get_cdi_annual(),
            selic_annual=OpportunityEngine._get_selic_annual(),
            user_profile=user_profile,
        )
    except Exception as exc:
        logger.error("[Tool] get_best_bank | user=%s: %s", user_id, exc)
        return "Não consegui montar o ranking de bancos agora. Tente novamente em instantes."

    weights = result.profile_used.get("weights", {})
    lines = [
        "=== MELHOR BANCO PARA VOCÊ (Bank Match) ===",
        "",
        f"Perfil considerado: FSS {result.profile_used.get('fss_level')} | "
        f"investidor {result.profile_used.get('investor_type')} | "
        f"pesos: rendimento {weights.get('yield', 0):.0%}, tarifas {weights.get('fees', 0):.0%}, "
        f"cartões {weights.get('card', 0):.0%}, perfil {weights.get('fit', 0):.0%}",
        f"Valor simulado: R$ {result.amount_simulated:,.2f} por {result.holding_months} meses",
        "",
        "── Top 5 bancos pelo seu perfil ──",
    ]

    for i, entry in enumerate(result.ranking[:5], start=1):
        marker = " ← seu banco atual" if entry.is_user_current_bank else ""
        lines.append(
            f"{i}. {entry.bank_name} — match {entry.match_score:.0f}/100 "
            f"(rende R$ {entry.projected_annual_gain_brl:,.2f}/ano no melhor produto)"
            f"{marker}"
        )
        if entry.top_card_name:
            lines.append(f"   💳 Cartão destaque: {entry.top_card_name}")

    if result.user_current_bank and result.user_current_bank_rank:
        lines += [
            "",
            f"📍 Seu banco atual ({result.user_current_bank}) está em "
            f"{result.user_current_bank_rank}º de {len(result.ranking)}.",
        ]

    lines += ["", result.switch_recommendation]

    from app.opportunities.models import DISCLAIMER
    lines += ["", DISCLAIMER]

    return "\n".join(lines)
