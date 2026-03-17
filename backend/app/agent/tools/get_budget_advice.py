# app/agent/tools/get_budget_advice.py
"""
Tool: get_budget_advice
Gera sugestões de orçamento baseadas na regra 50/30/20 (M1.3).
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
    Analisa os gastos REAIS do usuário (do banco de dados) e compara com os
    limites recomendados por categoria.

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

        # Buscar transações REAIS do DuckDB
        runner = NexaRunner(mode="dev")
        transactions_df = pl.DataFrame()

        result = runner.run_from_db(user_id=user_id, horizon_days=30)
        if result and result.get("status") == "success":
            transactions_df = result.get("transactions", {}).get("clean_df", pl.DataFrame())
            logger.info(f"[Tool] Usando {len(transactions_df)} transações reais do DuckDB")

            # Tentar pegar renda real do perfil se não foi informada
            income_profile = result.get("analysis", {}).get("income_profile")
            if not monthly_income and income_profile and income_profile.confidence >= 0.5:
                monthly_income = income_profile.monthly_net_income
                logger.info(f"[Tool] Renda estimada pelo IncomeProfiler: R$ {monthly_income:.0f}")
        else:
            logger.warning(f"[Tool] Sem dados no DuckDB para user={user_id}")

        advisor = BudgetAdvisor()
        suggestion = advisor.suggest(
            transactions_df=transactions_df,
            monthly_income=monthly_income,
        )

        data_source = "💾 *Análise baseada nos seus gastos reais*" if not transactions_df.is_empty() else "📊 *Análise teórica (sem transações conectadas)*"

        lines = [
            f"📋 **Plano de Orçamento 50/30/20 — Renda: R$ {monthly_income:,.0f}/mês**",
            data_source,
            "",
        ]

        # Grupos
        group_labels = {
            "essenciais": "🏠 Essenciais (50% recomendado)",
            "desejos": "🎯 Desejos / Qualidade de vida (30%)",
            "poupanca": "💰 Poupança / Investimentos (20%)",
        }

        for g in suggestion.group_summary:
            label  = group_labels.get(g.group, g.group)
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
        essenciais = monthly_income * 0.50
        desejos    = monthly_income * 0.30
        poupanca   = monthly_income * 0.20
        return (
            f"📋 **Plano 50/30/20 para renda de R$ {monthly_income:,.0f}/mês:**\n\n"
            f"🏠 Essenciais (moradia, alimentação, saúde, transporte): até R$ {essenciais:,.0f}/mês\n"
            f"🎯 Desejos (lazer, assinaturas, vestuário): até R$ {desejos:,.0f}/mês\n"
            f"💰 Poupança e investimentos: R$ {poupanca:,.0f}/mês\n\n"
            "Para uma análise com seus dados reais, as transações precisam estar disponíveis."
        )
