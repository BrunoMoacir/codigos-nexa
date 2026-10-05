# app/agent/tools/get_negotiation_script.py
import logging

from langchain_core.tools import tool

from app.core.db.queries import get_transactions_for_user
from app.negotiator.health_score import score_nexa
from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
from app.negotiator.script_generator import NegotiationScriptGenerator
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


@tool
def get_negotiation_script(user_id: str, bank_name: str = "") -> str:
    """
    Detecta oportunidades de negociação bancária e gera um roteiro personalizado via IA.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Como negocio minha anuidade / taxa de juros com o banco?"
    - "Posso pedir isenção da anuidade do meu cartão?"
    - "Meu banco está me cobrando juros altos, o que faço?"
    - "Me dá um script para falar com o gerente sobre redução de tarifas."
    - "Tenho poder de barganha com meu banco?"
    - Qualquer pedido de ajuda para negociar com banco.

    Args:
        user_id:   ID do usuário (obrigatório).
        bank_name: Nome do banco específico para filtrar (opcional). Se vazio, analisa todos.
    """
    logger.info("[Tool] get_negotiation_script | user=%s bank=%s", user_id, bank_name or "*")

    transactions_df = get_transactions_for_user(user_id)

    if transactions_df.is_empty():
        return (
            "Não encontrei histórico de transações para analisar oportunidades de negociação. "
            "Conecte sua conta bancária via Open Finance para obter essa análise."
        )

    # Fonte única — a cópia local importava `app.profile`, que não existe,
    # e o except devolvia 50 para todo usuário.
    health_score = score_nexa(transactions_df)

    # Detectar oportunidades
    detector = NegotiationOpportunityDetector()
    opportunities = detector.detect(transactions_df, health_score=health_score)

    if bank_name:
        bank_lower = bank_name.lower()
        opportunities = [o for o in opportunities if o.bank_name.lower() == bank_lower]

    if not opportunities:
        trecho = (
            f" (Score Nexa: {health_score}/100)" if health_score is not None else ""
        )
        return (
            f"Não detectei oportunidades de negociação no momento{trecho}. "
            "Continue sem juros rotativos para aumentar seu poder de barganha nos próximos meses."
        )

    # Gerar scripts
    generator = NegotiationScriptGenerator()
    cabecalho_score = (
        f"Score Nexa: {health_score}/100 | " if health_score is not None
        else "Score Nexa indisponível | "
    )
    lines = [
        "=== ROTEIRO DE NEGOCIAÇÃO BANCÁRIA ===",
        f"{cabecalho_score}{len(opportunities)} oportunidade(s) detectada(s)",
        "",
    ]

    for i, opp in enumerate(opportunities, 1):
        script = generator.generate(opp)
        lines += [
            f"── Oportunidade {i}: {opp.trigger.value} — {opp.bank_name} ──",
            f"Produto: {opp.product}",
        ]
        if opp.potential_saving_monthly > 0:
            lines.append(f"Economia potencial: {brl(opp.potential_saving_monthly)}/mês")
        lines += [
            "",
            f"ABERTURA: {script.opening_line}",
            "",
            "ARGUMENTOS:",
        ]
        for arg in script.key_arguments:
            lines.append(f"  • {arg}")
        lines += [
            "",
            f"PEÇA PRINCIPAL: {script.target_ask}",
            f"ALTERNATIVA:    {script.fallback_ask}",
            f"ENCERRAMENTO:   {script.closing_line}",
            "",
            f"Canal recomendado: {script.recommended_channel.value}",
            f"Melhor horário:    {script.best_time}",
            f"Chance de sucesso: {script.estimated_success_pct}%",
        ]
        if script.warnings:
            lines.append(f"Atenção: {'; '.join(script.warnings)}")
        lines.append("")

    return "\n".join(lines)



