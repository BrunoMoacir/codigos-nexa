# app/agent/tools/get_budget_advice.py
"""
Tool: get_budget_advice
Gera sugestões de orçamento baseadas na regra 50/30/20 (M1.3).

Use SEMPRE que o usuário perguntar sobre:
- Como organizar / distribuir o orçamento
- Quanto deveria gastar em cada categoria
- Se está gastando demais em alguma área
- Planejamento financeiro / metas de gastos
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_budget_advice(
    user_id: str,
    monthly_income: float,
) -> str:
    """
    Gera um plano de orçamento personalizado baseado na regra 50/30/20.
    Analisa os gastos reais do usuário e compara com os limites recomendados.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Como deve dividir o orçamento
    - Quanto deveria gastar em cada categoria (moradia, alimentação, lazer, poupança)
    - Se seus gastos estão adequados para sua renda
    - Planejamento de gastos / orçamento mensal

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal do usuário em reais (obrigatório).
    """
    logger.info(f"[Tool] get_budget_advice para {user_id}, renda=R${monthly_income:.0f}")
    try:
        from app.cashflow.budget_advisor import BudgetAdvisor
        from app.runner import NexaRunner
        import polars as pl

        # Tentar buscar transações reais
        try:
            runner = NexaRunner(mode="dev")
            result = runner.run(horizon_days=30)
            transactions_df = result.get("transactions_df", pl.DataFrame())
        except Exception:
            transactions_df = pl.DataFrame()


        advisor = BudgetAdvisor()
        suggestion = advisor.suggest(
            transactions_df=transactions_df,
            monthly_income=monthly_income,
        )

        lines = [
            f"📋 **Plano de Orçamento 50/30/20 — Renda: R$ {monthly_income:,.0f}/mês**",
            "",
        ]

        # Grupos
        group_labels = {
            "essenciais": "🏠 Essenciais (50% recomendado)",
            "desejos": "🎯 Desejos / Qualidade de vida (30%)",
            "poupanca": "💰 Poupança / Investimentos (20%)",
        }

        for g in suggestion.group_summary:
            label = group_labels.get(g.group, g.group)
            status = "✅" if g.on_track else "⚠️"
            lines.append(
                f"{status} {label}: "
                f"R$ {g.actual_spent:,.0f} gastos / "
                f"R$ {g.recommended_limit:,.0f} recomendado "
                f"({g.pct_of_income:.0%} da renda)"
            )

        lines.append("")

        # Cortes sugeridos
        if suggestion.suggested_cuts:
            lines.append("✂️ **Onde reduzir:**")
            for cut in suggestion.suggested_cuts[:3]:
                lines.append(
                    f"   • {cut.category}: gastar R$ {cut.suggested_limit:,.0f} "
                    f"ao invés de R$ {cut.current_spending:,.0f} "
                    f"(economia: R$ {cut.potential_saving:,.0f}/mês)"
                )
            lines.append("")

        lines.append(f"📝 {suggestion.summary_text}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[Tool] get_budget_advice erro: {e}", exc_info=True)
        # Resposta manual sem dados
        essenciais = monthly_income * 0.50
        desejos = monthly_income * 0.30
        poupanca = monthly_income * 0.20
        return (
            f"📋 **Plano 50/30/20 para renda de R$ {monthly_income:,.0f}/mês:**\n\n"
            f"🏠 Essenciais (moradia, alimentação, saúde, transporte): até R$ {essenciais:,.0f}/mês\n"
            f"🎯 Desejos (lazer, assinaturas, vestuário): até R$ {desejos:,.0f}/mês\n"
            f"💰 Poupança e investimentos: R$ {poupanca:,.0f}/mês\n\n"
            "Para uma análise personalizada com seus gastos reais, conecte suas contas bancárias via Open Finance."
        )
