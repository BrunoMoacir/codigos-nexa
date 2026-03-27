# app/agent/tools/get_financial_forecast.py
"""
Tool: get_financial_forecast
Retorna o resumo financeiro completo do usuário — cashflow, safe-to-spend,
health score, alertas ativos e padrão de renda estimado.
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

        # Busca dados REAIS do banco para este usuário
        result = runner.run_from_db(user_id=user_id, horizon_days=horizon_days)

        if result is None:
            # Sem dados = usuário não conectou banco ainda. NÃO usar mock.
            logger.warning(f"[Tool] Sem dados no banco para user={user_id}")
            return (
                "Ainda não há transações conectadas para este usuário. "
                "Para ver o diagnóstico financeiro real, conecte uma conta bancária via Open Finance "
                "na seção 'Conectar conta' do aplicativo."
            )

        if not result or result.get("status") != "success":
            return (
                "Não consegui carregar dados financeiros para este usuário no momento. "
                "Verifique se há transações conectadas via Open Finance."
            )

        proj          = result.get("projections", {})
        safe          = proj.get("safe_to_spend")
        analysis      = result.get("analysis", {})
        income_profile = analysis.get("income_profile")
        profile        = result.get("user_profile")  # disponível no run() mock

        lines = ["📊 **Diagnóstico Financeiro Nexa**", ""]

        # Safe-to-spend
        if safe:
            lines.append("💰 **Margem disponível para gastar:**")
            lines.append(f"   • Este mês: R$ {safe.safe_to_spend_total:,.2f}")
            lines.append(f"   • Por dia com segurança: R$ {safe.safe_to_spend_daily:,.2f}")
            lines.append(f"   • Nível de risco: {safe.risk_level}")
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
            profile_type = getattr(profile, "profile_type", "EQUILIBRADO")
            lines.append(f"🏥 Health Score: {score}/100 (tendência: {trend})")
            lines.append(f"   Perfil: {profile_type}")
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
            if hasattr(cf, "ending_balance"):
                lines.append(f"   • Saldo esperado ao fim: R$ {cf.ending_balance:,.2f}")
            elif hasattr(cf, "expected_balance"):
                lines.append(f"   • Saldo esperado ao fim: R$ {cf.expected_balance:,.2f}")
            if hasattr(cf, "monthly_income"):
                lines.append(f"   • Receita estimada: R$ {cf.monthly_income:,.2f}")
            if hasattr(cf, "monthly_expense"):
                lines.append(f"   • Despesas estimadas: R$ {cf.monthly_expense:,.2f}")
            if hasattr(cf, "worst_balance"):
                lines.append(f"   • Pior saldo projetado: R$ {cf.worst_balance:,.2f}")
            lines.append("")

        # Shadow invoices
        shadow = result.get("shadow_invoices", {})
        if shadow:
            total_impact = shadow.get("total_monthly_impact", 0)
            count = shadow.get("total_count", 0)
            if count > 0:
                lines.append(f"👻 **Obrigações futuras:** {count} itens detectados")
                lines.append(f"   • Impacto mensal: R$ {abs(total_impact):,.2f}")
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
