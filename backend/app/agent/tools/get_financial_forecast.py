# app/agent/tools/get_financial_forecast.py
"""
Tool: get_financial_forecast
Retorna o resumo financeiro completo do usuário — cashflow, safe-to-spend,
health score, alertas ativos e padrão de renda estimado.

Use SEMPRE que o usuário pedir:
- Resumo do perfil / situação financeira
- Quanto pode gastar esse mês
- Como estão as finanças
- Saldo seguro / margem disponível
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_financial_forecast(
    user_id: str,
    monthly_income: Optional[float] = None,
    horizon_days: int = 30,
) -> str:
    """
    Busca o diagnóstico financeiro completo do usuário: cashflow, safe-to-spend,
    health score, projeção de saldo, renda estimada e alertas.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Resumo da situação financeira
    - Quanto pode gastar / margem disponível
    - Como estão as finanças este mês
    - Saúde financeira (health score)

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal declarada (opcional — melhora a análise).
        horizon_days: Horizonte de projeção em dias (padrão: 30).
    """
    logger.info(f"[Tool] get_financial_forecast para {user_id}")
    try:
        from app.runner import NexaRunner

        runner = NexaRunner(mode="dev")
        result = runner.run(horizon_days=horizon_days)

        if result.get("status") != "success":
            return (
                "Não consegui carregar dados financeiros para este usuário no momento. "
                "Verifique se há transações conectadas via Open Finance."
            )

        proj = result.get("projections", {})
        safe = proj.get("safe_to_spend")
        profile = result.get("user_profile")
        income_profile = result.get("income_profile")

        lines = ["📊 **Diagnóstico Financeiro Nexa**", ""]

        # Safe-to-spend
        if safe:
            lines.append(f"💰 **Margem disponível para gastar:**")
            lines.append(f"   • Este mês: R$ {safe.safe_to_spend_total:,.2f}")
            lines.append(f"   • Por dia com segurança: R$ {safe.safe_to_spend_daily:,.2f}")
            lines.append("")

        # Renda
        if monthly_income:
            lines.append(f"💵 Renda declarada: R$ {monthly_income:,.0f}/mês")
        elif income_profile and income_profile.confidence >= 0.5:
            lines.append(
                f"💵 Renda estimada: R$ {income_profile.monthly_net_income:,.0f}/mês "
                f"(padrão {income_profile.income_pattern.value}, "
                f"confiança {income_profile.confidence:.0%})"
            )

        # Health score
        if profile:
            score = profile.financial_health_score
            trend = profile.trend
            lines.append(f"🏥 Health Score: {score}/100 (tendência: {trend})")
            lines.append(f"   Perfil: {profile.summary if hasattr(profile, 'summary') else profile.profile_type}")
            lines.append("")

        # Cashflow forecast
        cf = proj.get("cashflow_forecast")
        import polars as pl
        cf_has_data = (
            cf is not None
            and not (isinstance(cf, pl.DataFrame) and cf.is_empty())
        )
        if cf_has_data:
            lines.append("📈 **Projeção de Cashflow (30 dias):**")
            if hasattr(cf, "expected_balance"):
                lines.append(f"   • Saldo esperado ao fim: R$ {cf.expected_balance:,.2f}")
            if hasattr(cf, "monthly_income"):
                lines.append(f"   • Receita estimada: R$ {cf.monthly_income:,.2f}")
            if hasattr(cf, "monthly_expense"):
                lines.append(f"   • Despesas estimadas: R$ {cf.monthly_expense:,.2f}")
            lines.append("")

        return "\n".join(lines) if len(lines) > 2 else (
            "Diagnóstico calculado, mas sem dados históricos suficientes para montar o relatório completo. "
            "Conecte mais contas bancárias via Open Finance para uma análise mais precisa."
        )

    except Exception as e:
        logger.error(f"[Tool] get_financial_forecast erro: {e}", exc_info=True)
        return (
            "Não consegui acessar os dados financeiros agora. "
            "Tente novamente ou informe sua renda e gastos mensais para uma análise manual."
        )
