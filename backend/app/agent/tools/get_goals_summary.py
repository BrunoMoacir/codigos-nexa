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
        # Dois erros moravam aqui e o except os escondia atrás de "Não consegui
        # acessar suas metas no momento":
        #   1. `GoalTracker()` sem sessão — `list_goals` chama `_require_db()` e
        #      levanta RuntimeError em TODA chamada (mesmo defeito de F7 e F13);
        #   2. o retorno é `list[Goal]` (dataclass), não `{"goals": [...]}` de
        #      dicionários — `.get("goals", [])` devolveria vazio mesmo que a
        #      consulta funcionasse, e a tool diria "você não tem metas" para
        #      quem tem.
        from app.core.database import SessionLocal
        from app.goals.tracker import GoalTracker

        with SessionLocal() as db:
            tracker = GoalTracker(db)
            goals = tracker.list_goals(user_id=user_id, status="ACTIVE")
            projecoes = {}
            for goal in goals:
                try:
                    projecoes[goal.goal_id] = tracker.get_projection(goal)
                except Exception as exc:  # projeção é enfeite; meta é o dado
                    logger.debug("[Tool] projeção da meta %s indisponível: %s",
                                 goal.goal_id, exc)

        if not goals:
            return (
                "Você ainda não tem metas financeiras cadastradas. "
                "Posso ajudá-lo a criar uma! Diga sua meta (ex: reserva de emergência de R$ 20.000) "
                "e quando pretende atingi-la."
            )

        lines = [f"🎯 **Suas Metas Financeiras** ({len(goals)} ativa(s))", ""]

        for goal in goals:
            name = goal.name
            target = goal.target_amount or 0.0
            current = goal.current_amount or 0.0
            pct = goal.progress_pct
            remaining = max(0.0, target - current)

            # Barra de progresso visual
            filled = int(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)

            lines.append(f"📌 **{name}**")
            lines.append(f"   [{bar}] {pct:.0f}%")
            lines.append(f"   R$ {current:,.0f} de R$ {target:,.0f} (faltam R$ {remaining:,.0f})")

            # Projeção (GoalProjection: on_track, projected_completion_date,
            # months_remaining) — não um dicionário com "status"/"estimated_*".
            proj = projecoes.get(goal.goal_id)
            eta = getattr(proj, "projected_completion_date", None) if proj else None
            if remaining <= 0:
                lines.append("   ✅ Meta atingida!")
            elif eta:
                rumo = "no rumo" if getattr(proj, "on_track", False) else "atrasada"
                lines.append(f"   📅 Estimativa: {eta[:10]} ({rumo})")

            # Se temos monthly_savings, calcular projeção simples
            if monthly_savings and remaining > 0 and not eta:
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
