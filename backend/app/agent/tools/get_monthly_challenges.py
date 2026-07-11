# app/agent/tools/get_monthly_challenges.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_STATUS_LABEL = {
    "ACTIVE":    "🎯 EM ANDAMENTO",
    "COMPLETED": "🏅 CONCLUÍDO",
    "FAILED":    "❌ NÃO ROLOU",
}


@tool
def get_monthly_challenges(user_id: str) -> str:
    """
    Retorna os desafios financeiros do mês do usuário (gamificação do
    Health Score): mês sem tarifas, redução de categoria, meta de poupança
    e subida de score — com progresso atual e badges conquistados.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Quais são meus desafios do mês?"
    - "Como está meu desafio de economizar?"
    - "Ganhei algum badge?"
    - "Como faço para subir meu score?" (contexto de gamificação)
    - Qualquer pergunta sobre desafios, conquistas ou metas mensais do app.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_monthly_challenges | user=%s", user_id)

    try:
        from app.health_score.challenge_service import get_challenge_service

        service = get_challenge_service()
        challenges = service.sync(user_id)
    except Exception as exc:
        logger.error("[Tool] get_monthly_challenges erro: %s", exc)
        return f"Erro ao consultar os desafios do mês: {exc}"

    lines = ["=== DESAFIOS DO MÊS (R2.b) ===", ""]

    if not challenges:
        lines.append(
            "Nenhum desafio gerado ainda — os desafios são criados a partir "
            "dos dados reais das contas conectadas. Conecte uma conta via "
            "Open Finance para receber desafios personalizados."
        )
        return "\n".join(lines)

    for ch in challenges:
        label = _STATUS_LABEL.get(ch.status, ch.status)
        lines += [
            f"── {ch.title} ──",
            f"Status: {label} · Progresso: {ch.pct_progress:.0f}%",
            f"Alvo: {ch.target_label}",
        ]
        detail = service._progress_detail(ch)
        if detail:
            lines.append(detail)
        lines.append("")

    # Badges de desafio já conquistados
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT badge_type FROM user_badges"
                    " WHERE user_id = :uid AND badge_type IN"
                    " ('PRIMEIRO_DESAFIO', 'DESAFIO_TRIPLO', 'DESAFIO_STREAK_3')"
                ),
                {"uid": user_id},
            ).fetchall()
        if rows:
            lines.append("Badges de desafio: " + ", ".join(r[0] for r in rows))
    except Exception:
        pass

    lines.append(
        "Complete desafios para ganhar badges — e para transformar economia "
        "pontual em hábito. Os desafios renovam todo início de mês."
    )
    return "\n".join(lines)
