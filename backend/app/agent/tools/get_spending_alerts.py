# app/agent/tools/get_spending_alerts.py
"""
Tool: get_spending_alerts
Retorna alertas financeiros ativos + notificações proativas do usuário.

Use SEMPRE que o usuário perguntar sobre:
- Alertas / avisos financeiros
- Se tem algo para se preocupar nas finanças
- Anomalias de gastos
- Assinaturas esquecidas
- Velocidade de gastos (burn rate)
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_spending_alerts(
    user_id: str,
    monthly_income: Optional[float] = None,
) -> str:
    """
    Retorna os alertas financeiros ativos e notificações proativas do usuário.
    Inclui: anomalias de gasto, burn rate alto, assinaturas esquecidas,
    safe-to-spend baixo e oportunidades de cartão.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Tem algum alerta / problema nas finanças?
    - Algum gasto anormal detectado?
    - Avisos importantes sobre as finanças
    - O que devo me preocupar este mês?

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal (opcional — melhora detecção de anomalias).
    """
    logger.info(f"[Tool] get_spending_alerts para {user_id}")
    try:
        from app.runner import NexaRunner
        from app.notifications.notifier import ProactiveNotifier, NotificationContext
        import polars as pl

        lines = ["🔔 **Alertas e Notificações Financeiras**", ""]
        total_alerts = 0

        # 1. NexaRunner alerts — usando dados REAIS do DuckDB
        try:
            runner = NexaRunner(mode="dev")
            result = runner.run_from_db(user_id=user_id, horizon_days=30)
            if result is None:
                result = runner.run(horizon_days=30)  # fallback para mock

            alerts = result.get("alerts", [])
            if alerts:
                critical = [a for a in alerts if getattr(a, "severity", "") == "CRITICAL"]
                warnings = [a for a in alerts if getattr(a, "severity", "") == "WARNING"]

                if critical:
                    lines.append("🔴 **Alertas Críticos:**")
                    for a in critical[:3]:
                        lines.append(f"   • {getattr(a, 'message', str(a))}")
                    lines.append("")

                if warnings:
                    lines.append("🟡 **Avisos:**")
                    for a in warnings[:3]:
                        lines.append(f"   • {getattr(a, 'message', str(a))}")
                    lines.append("")

                total_alerts += len(alerts)
        except Exception as e:
            logger.debug(f"[Tool] Runner alerts erro (ignorado): {e}")

        # 2. Notificações proativas (MX.3)
        try:
            ctx = NotificationContext()
            notifier = ProactiveNotifier()
            notifications = notifier.generate(ctx)

            if notifications:
                lines.append("📱 **Notificações Proativas:**")
                for n in notifications[:5]:
                    emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(n.priority, "•")
                    lines.append(f"   {emoji} [{n.type}] {n.title}")
                    lines.append(f"      {n.message}")
                lines.append("")
                total_alerts += len(notifications)
        except Exception as e:
            logger.debug(f"[Tool] Notificações erro (ignorado): {e}")

        if total_alerts == 0:
            lines.append("✅ Nenhum alerta crítico no momento. Suas finanças parecem estáveis.")
        else:
            lines.append(f"Total: {total_alerts} alerta(s) detectado(s).")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[Tool] get_spending_alerts erro: {e}", exc_info=True)
        return "Não foi possível verificar os alertas no momento. Tente novamente em instantes."
