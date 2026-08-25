# app/agent/tools/get_budget_advice.py
"""
Tool: get_budget_advice
Gera sugestões de orçamento baseadas na regra 50/30/20 (M1.3).
"""
from app.agent.procedencia import com_procedencia, degradada
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_budget_advice(
    user_id: str,
    monthly_income: Optional[float] = None,
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
        monthly_income: Renda mensal em reais. OPCIONAL — informe apenas se o
            usuário declarou um valor. Deixe em branco para a Nexa estimar a
            renda pelo extrato (IncomeProfiler). NUNCA invente um valor.
    """
    # `monthly_income` era OBRIGATÓRIO, e o fallback do IncomeProfiler logo
    # abaixo está atrás de `if not monthly_income` — ou seja, era inalcançável:
    # o modelo tinha de mandar algum número, e o prompt nunca disse para mandar
    # zero. Na prática, o plano 50/30/20 saía sobre uma renda que o LLM
    # escolheu, com o rótulo "baseada nos seus gastos reais" em cima.
    logger.info(
        "[Tool] get_budget_advice para %s, renda declarada=%s",
        user_id, f"R${monthly_income:.0f}" if monthly_income else "não informada",
    )
    renda_declarada = bool(monthly_income and monthly_income > 0)
    try:
        from app.budget.budget_advisor import BudgetAdvisor
        from app.runner import get_runner
        import polars as pl

        renda_estimada = False

        # Buscar transações REAIS do DuckDB
        transactions_df = pl.DataFrame()

        result = get_runner().run_from_db(user_id=user_id, horizon_days=30)
        if result and result.get("status") == "success":
            transactions_df = result.get("transactions", {}).get("clean_df", pl.DataFrame())
            logger.info("[Tool] Usando %s transações reais do DuckDB", len(transactions_df))

            # Tentar pegar renda real do perfil se não foi informada
            income_profile = result.get("analysis", {}).get("income_profile")
            if not renda_declarada and income_profile and income_profile.confidence >= 0.5:
                monthly_income = income_profile.monthly_net_income
                renda_estimada = True
                logger.info("[Tool] Renda estimada pelo IncomeProfiler: R$ %.0f", monthly_income)
        else:
            logger.warning("[Tool] Sem dados no DuckDB para user=%s", user_id)

        if not monthly_income or monthly_income <= 0:
            return (
                "FALHA: não há renda para montar o 50/30/20 — o usuário não "
                "declarou nenhuma e o extrato não permitiu estimar com "
                "confiança. PERGUNTE a renda mensal líquida ao usuário e chame "
                "de novo. Não invente um valor."
            )

        advisor = BudgetAdvisor()
        suggestion = advisor.suggest(
            transactions_df=transactions_df,
            monthly_income=monthly_income,
        )

        # O rótulo dizia respeito só às TRANSAÇÕES: com gastos reais e uma renda
        # que o modelo informou, saía "baseada nos seus gastos reais" — e a
        # renda, que define todos os limites, podia ser um chute. Agora as duas
        # procedências aparecem separadas.
        origem_gastos = (
            "gastos reais do seu extrato" if not transactions_df.is_empty()
            else "sem transações conectadas (análise teórica)"
        )
        origem_renda = (
            "renda informada por você" if renda_declarada
            else "renda estimada pelo seu extrato" if renda_estimada
            else "renda não confirmada"
        )

        lines = [
            f"📋 **Plano de Orçamento 50/30/20 — Renda: R$ {monthly_income:,.0f}/mês**",
            f"💾 *Base: {origem_gastos} · {origem_renda}*",
            "",
        ]

        # Grupos
        group_labels = {
            "essenciais": "🏠 Essenciais (50% recomendado)",
            "desejos": "🎯 Desejos / Qualidade de vida (30%)",
            "poupanca": "💰 Poupança / Investimentos (20%)",
        }

        # Os nomes abaixo eram SEIS invenções — `on_track`, `actual_spent`,
        # `recommended_limit`, `pct_of_income`, `suggested_cuts`,
        # `suggested_limit`/`current_spending`/`potential_saving`. O
        # `AttributeError` no primeiro deles caía no `except` da tool, que
        # devolvia o 50/30/20 genérico. Resultado: a análise dos gastos reais
        # prometida no docstring NUNCA chegou ao usuário — a tool sempre
        # respondeu com o template. Os nomes reais estão em
        # `app/budget/budget_advisor.py` (GroupSummary, BudgetCut).
        icone_por_status = {"WITHIN": "✅", "OVER": "⚠️", "UNDER": "🔽"}

        for g in suggestion.group_summary:
            label = group_labels.get(g.group, g.group)
            icone = icone_por_status.get(g.status, "•")
            lines.append(
                f"{icone} {label}: "
                f"R$ {g.current_amount:,.0f} gastos / "
                f"R$ {g.suggested_amount:,.0f} recomendado "
                f"({g.current_pct:.0%} da renda)"
            )

        lines.append("")

        # Cortes sugeridos
        if suggestion.actionable_cuts:
            lines.append("✂️ **Onde reduzir:**")
            for cut in suggestion.actionable_cuts[:3]:
                lines.append(
                    f"   • {cut.category}: gastar R$ {cut.suggested:,.0f} "
                    f"ao invés de R$ {cut.current:,.0f} "
                    f"(economia: R$ {cut.saving:,.0f}/mês)"
                )
            lines.append("")

        lines.append(f"📝 {suggestion.summary_text}")

        fontes = ["budget_advisor"]
        if not transactions_df.is_empty():
            fontes.append("transactions_db")
        if renda_estimada:
            fontes.append("income_profiler")

        return com_procedencia(
            "\n".join(lines),
            fontes=fontes,
            confianca=getattr(suggestion, "confidence", None),
            cobertura_meses=getattr(suggestion, "history_months", None),
        )

    except Exception as e:
        logger.error("[Tool] get_budget_advice erro: %s", e, exc_info=True)
        if not monthly_income or monthly_income <= 0:
            return (
                "FALHA: não consegui montar o orçamento e não tenho renda para "
                "o plano genérico. PERGUNTE a renda mensal líquida ao usuário."
            )
        essenciais = monthly_income * 0.50
        desejos    = monthly_income * 0.30
        poupanca   = monthly_income * 0.20
        return degradada(
            f"📋 **Plano 50/30/20 para renda de R$ {monthly_income:,.0f}/mês:**\n\n"
            f"🏠 Essenciais (moradia, alimentação, saúde, transporte): até R$ {essenciais:,.0f}/mês\n"
            f"🎯 Desejos (lazer, assinaturas, vestuário): até R$ {desejos:,.0f}/mês\n"
            f"💰 Poupança e investimentos: R$ {poupanca:,.0f}/mês\n\n"
            "Para uma análise com seus dados reais, as transações precisam estar disponíveis.",
            "advisor_falhou",
        )
