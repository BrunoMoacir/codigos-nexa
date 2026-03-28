# app/agent/tools/get_goals_summary.py
"""
Tool: get_goals_summary
Retorna o progresso das metas financeiras do usuário (MX.2).

Use SEMPRE que o usuário perguntar sobre:
- Suas metas financeiras / objetivos
- Progresso de poupança para algum objetivo
- Quando vai atingir uma meta
- Reserva de emergência, viagem, imóvel, etc.
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_goals_summary(
    user_id: str,
    monthly_savings: Optional[float] = None,
) -> str:
    """
    Busca e resume as metas financeiras ativas do usuário, incluindo progresso
    percentual, valor restante e projeção de quando vai atingir cada meta.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Suas metas financeiras / objetivos de poupança
    - Reserva de emergência, viagem, imóvel, aposentadoria
    - Progresso em uma meta específica
    - Quanto falta para atingir um objetivo

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_savings: Quanto o usuário consegue poupar por mês (opcional — melhora projeção).
    """
    logger.info("[Tool] get_goals_summary para %s", user_id)
    try:
        from app.goals.tracker import GoalTracker

        tracker = GoalTracker()
        goals_data = tracker.list_goals(user_id=user_id)

        goals = goals_data.get("goals", [])

        if not goals:
            return (
                "Você ainda não tem metas financeiras cadastradas. "
                "Posso ajudá-lo a criar uma! Diga sua meta (ex: reserva de emergência de R$ 20.000) "
                "e quando pretende atingi-la."
            )

        lines = [f"🎯 **Suas Metas Financeiras** ({len(goals)} ativa(s))", ""]

        for goal in goals:
            name = goal.get("name", "Meta")
            target = goal.get("target_amount", 0)
            current = goal.get("current_amount", 0)
            pct = (current / target * 100) if target > 0 else 0
            remaining = target - current

            # Barra de progresso visual
            filled = int(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)

            lines.append(f"📌 **{name}**")
            lines.append(f"   [{bar}] {pct:.0f}%")
            lines.append(f"   R$ {current:,.0f} de R$ {target:,.0f} (faltam R$ {remaining:,.0f})")

            # Projeção
            proj = goal.get("projection", {})
            if proj:
                status = proj.get("status", "")
                eta = proj.get("estimated_completion_date")
                if eta and status != "COMPLETED":
                    lines.append(f"   📅 Estimativa: {eta[:10] if eta else 'indefinida'}")
                elif status == "COMPLETED":
                    lines.append(f"   ✅ Meta atingida!")

            # Se temos monthly_savings, calcular projeção simples
            if monthly_savings and remaining > 0 and not proj.get("estimated_completion_date"):
                months_needed = remaining / monthly_savings
                lines.append(f"   ⏳ Com R$ {monthly_savings:,.0f}/mês → {months_needed:.0f} meses para atingir")

            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error("[Tool] get_goals_summary erro: %s", e, exc_info=True)
        return (
            "Não consegui acessar suas metas no momento. "
            "Se quiser criar uma nova meta, me diga o valor objetivo e o prazo."
        )
