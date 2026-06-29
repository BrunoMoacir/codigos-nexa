# app/agent/tools/get_annual_wrapped.py
import logging
from datetime import date

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_annual_wrapped(user_id: str, year: int = 0) -> str:
    """
    Gera o resumo anual "Banco vs Você" — o Wrapped financeiro do usuário.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Qual meu resumo financeiro do ano?"
    - "Como foi meu ano financeiro?"
    - "Qual foi minha evolução de score no ano?"
    - "Quanto paguei de tarifas no ano?"
    - "Meu Wrapped financeiro"
    - "Resumo anual das minhas finanças"
    - Qualquer pedido de balanço ou retrospectiva financeira anual.

    Args:
        user_id: ID do usuário (obrigatório).
        year:    Ano a analisar. 0 = ano corrente (padrão).
    """
    logger.info("[Tool] get_annual_wrapped | user=%s year=%s", user_id, year or "current")

    target_year = year if year > 0 else date.today().year
    year_prefix = str(target_year)

    score_data = _get_score_evolution(user_id, year_prefix)
    fee_data = _get_annual_fees(user_id, year_prefix)
    negotiation_data = _get_annual_negotiations(user_id, year_prefix)
    badge_data = _get_badges(user_id)

    lines = [
        f"=== WRAPPED FINANCEIRO {target_year} — SEU ANO VS. OS BANCOS ===",
        "",
    ]

    # Score evolution
    if score_data:
        first_score, last_score = score_data
        delta = last_score - first_score
        trend = "📈 subiu" if delta > 0 else ("📉 caiu" if delta < 0 else "→ estável")
        lines += [
            f"── Score de Saúde Financeira ──",
            f"Início do ano: {first_score}/100 → Final: {last_score}/100",
            f"Evolução: {trend} {abs(delta)} pontos",
            "",
        ]
    else:
        lines += ["── Score: histórico insuficiente para {target_year} ──", ""]

    # Fees paid
    if fee_data:
        total_fees, worst_bank, worst_fee_type = fee_data
        lines += [
            f"── Tarifas Pagas em {target_year} ──",
            f"Total pago em tarifas: R$ {total_fees:,.2f}",
        ]
        if worst_bank:
            lines.append(f"Banco que mais cobrou: {worst_bank}")
        if worst_fee_type:
            lines.append(f"Tarifa mais cara: {worst_fee_type}")
        lines.append("")
    else:
        lines += [f"── Tarifas: sem dados de {target_year} ──", ""]

    # Negotiation opportunities
    if negotiation_data:
        count, total_potential = negotiation_data
        lines += [
            f"── Oportunidades de Negociação ──",
            f"{count} oportunidade(s) identificada(s) no ano",
            f"Potencial de economia total: R$ {total_potential:,.2f}",
            f"Economia anual projetada: R$ {total_potential * 12:,.2f} (se todas concretizadas)",
            "",
        ]

    # Badges earned
    if badge_data:
        lines += [
            f"── Conquistas do Ano ──",
            ", ".join(badge_data),
            "",
        ]

    # Motivational close
    lines += [
        "── O que fazer em {next_year} ──".format(next_year=target_year + 1),
        "1. Mantenha o score acima de 70 por 3 meses seguidos para ganhar o badge 3_MESES_VERDE.",
        "2. Use o Negociador para converter as oportunidades acima em economia real.",
        "3. Mova dinheiro parado para LCI/LCA ou Tesouro Selic — cada R$ 1.000 parado "
        "custa ~R$ 8/mês de rendimento não capturado.",
        "",
        f"Fonte: health_score_history, bank_fee_history, negotiation_history — dados Nexa {target_year}.",
    ]

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────

def _get_score_evolution(user_id: str, year_prefix: str) -> tuple[int, int] | None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT health_score FROM health_score_history"
                    " WHERE user_id = :uid AND date LIKE :yp"
                    " ORDER BY date ASC"
                ),
                {"uid": user_id, "yp": f"{year_prefix}%"},
            ).fetchall()

        if len(rows) >= 2:
            return rows[0][0], rows[-1][0]
        if len(rows) == 1:
            return rows[0][0], rows[0][0]
    except Exception as exc:
        logger.debug("[get_annual_wrapped] _get_score_evolution: %s", exc)
    return None


def _get_annual_fees(user_id: str, year_prefix: str) -> tuple[float, str | None, str | None] | None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            total_row = db.execute(
                text(
                    "SELECT COALESCE(SUM(amount), 0) FROM bank_fee_history"
                    " WHERE user_id = :uid AND month LIKE :yp"
                ),
                {"uid": user_id, "yp": f"{year_prefix}%"},
            ).fetchone()

            worst_bank_row = db.execute(
                text(
                    "SELECT bank_name, SUM(amount) AS total FROM bank_fee_history"
                    " WHERE user_id = :uid AND month LIKE :yp"
                    " GROUP BY bank_name ORDER BY total DESC LIMIT 1"
                ),
                {"uid": user_id, "yp": f"{year_prefix}%"},
            ).fetchone()

            worst_fee_row = db.execute(
                text(
                    "SELECT fee_type, SUM(amount) AS total FROM bank_fee_history"
                    " WHERE user_id = :uid AND month LIKE :yp"
                    " GROUP BY fee_type ORDER BY total DESC LIMIT 1"
                ),
                {"uid": user_id, "yp": f"{year_prefix}%"},
            ).fetchone()

        total = float(total_row[0]) if total_row else 0.0
        if total == 0.0:
            return None
        worst_bank = worst_bank_row[0] if worst_bank_row else None
        worst_fee = worst_fee_row[0] if worst_fee_row else None
        return total, worst_bank, worst_fee
    except Exception as exc:
        logger.debug("[get_annual_wrapped] _get_annual_fees: %s", exc)
    return None


def _get_annual_negotiations(user_id: str, year_prefix: str) -> tuple[int, float] | None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COUNT(*), COALESCE(SUM(potential_gain), 0)"
                    " FROM negotiation_history"
                    " WHERE user_id = :uid AND CAST(generated_at AS TEXT) LIKE :yp"
                ),
                {"uid": user_id, "yp": f"{year_prefix}%"},
            ).fetchone()

        if row and row[0] > 0:
            return int(row[0]), float(row[1])
    except Exception as exc:
        logger.debug("[get_annual_wrapped] _get_annual_negotiations: %s", exc)
    return None


def _get_badges(user_id: str) -> list[str]:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text("SELECT badge_type FROM user_badges WHERE user_id = :uid ORDER BY earned_at"),
                {"uid": user_id},
            ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
