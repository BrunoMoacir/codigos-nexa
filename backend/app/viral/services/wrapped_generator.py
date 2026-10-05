"""
app/viral/services/wrapped_generator.py — V2: Wrapped Anual "Banco vs Você"

Gera 5 highlights do ano:

  biggest_waste    — categoria de tarifa com maior gasto total no ano
  worst_fee        — tarifa individual mais alta paga
  best_card_missed — cartão que mais renderia vs. cartão atual
  idle_money       — quanto ficou parado na conta sem render
  score_evolution  — evolução do Health Score no ano
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from app.viral.models import WrappedHighlight, WrappedReport
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


_MIN_MONTHS_FULL = 3


class WrappedGenerator:
    def generate(self, user_id: str, year: int) -> WrappedReport:
        months_active = self._months_active(user_id)
        is_partial = months_active < _MIN_MONTHS_FULL

        if is_partial:
            return self._educational_report(user_id, year, months_active)

        highlights: list[WrappedHighlight] = []
        total_fees = 0.0
        total_savings = 0.0

        h, fees = self._biggest_waste(user_id, year)
        if h:
            highlights.append(h)
            total_fees = fees

        h = self._worst_fee(user_id, year)
        if h:
            highlights.append(h)

        h, savings = self._best_card_missed(user_id)
        if h:
            highlights.append(h)
            total_savings += savings

        h, idle = self._idle_money(user_id)
        if h:
            highlights.append(h)
            total_savings += idle

        h, score_start, score_end = self._score_evolution(user_id, year)
        if h:
            highlights.append(h)

        badges = self._get_badges(user_id, year)
        score_delta = (score_end - score_start) if score_start and score_end else None

        summary = self._build_tagline(total_fees, total_savings, score_delta, badges, year)

        return WrappedReport(
            user_id=user_id,
            year=year,
            generated_at=_now_utc(),
            highlights=highlights,
            total_fees_paid_year=round(total_fees, 2),
            total_savings_identified=round(total_savings, 2),
            score_start=score_start,
            score_end=score_end,
            score_delta=score_delta,
            badges_earned=badges,
            summary_tagline=summary,
            # O ano corrente ainda não acabou: sem isso o card de 2026, em
            # outubro, se apresentava como retrospectiva fechada do ano.
            is_partial_year=year >= _now_utc().year,
        )

    def _educational_report(self, user_id: str, year: int, months: int) -> WrappedReport:
        summary = (
            f"Você está há {months} mês(es) na Nexa — continue usando para "
            f"desbloquear seu Wrapped completo de {year} em breve."
        )
        return WrappedReport(
            user_id=user_id,
            year=year,
            generated_at=_now_utc(),
            highlights=[],
            total_fees_paid_year=0.0,
            total_savings_identified=0.0,
            badges_earned=self._get_badges(user_id, year),
            summary_tagline=summary,
            is_partial_year=True,
        )

    @staticmethod
    def _months_active(user_id: str) -> int:
        try:
            from datetime import datetime, timezone

            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text("SELECT created_at FROM users WHERE user_id = :uid"),
                    {"uid": user_id},
                ).fetchone()

            if not row or not row[0]:
                return 1

            created_at = row[0]
            today = datetime.now(timezone.utc)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return max(1, (today.year - created_at.year) * 12 + today.month - created_at.month)
        except Exception:
            return 1

    # ── biggest_waste ────────────────────────────────────────────────

    def _biggest_waste(self, user_id: str, year: int) -> tuple[Optional[WrappedHighlight], float]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            month_start = f"{year}-01"
            month_end = f"{year}-12"
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT fee_type, SUM(amount) as total "
                        "FROM bank_fee_history "
                        "WHERE user_id = :uid AND month BETWEEN :m1 AND :m2 "
                        "GROUP BY fee_type ORDER BY total DESC LIMIT 1"
                    ),
                    {"uid": user_id, "m1": month_start, "m2": month_end},
                ).fetchone()

                total_fees = db.execute(
                    text(
                        "SELECT COALESCE(SUM(amount), 0) FROM bank_fee_history "
                        "WHERE user_id = :uid AND month BETWEEN :m1 AND :m2"
                    ),
                    {"uid": user_id, "m1": month_start, "m2": month_end},
                ).scalar() or 0.0

            if not rows:
                return None, 0.0

            fee_type, amount = rows
            h = WrappedHighlight(
                category="biggest_waste",
                title="Maior desperdício do ano",
                value_formatted=f"{brl(float(amount))}",
                description=(
                    f"Você pagou {brl(float(amount))} só em {_friendly_fee(fee_type)} em {year}. "
                    f"Total de tarifas no ano: {brl(float(total_fees))}."
                ),
            )
            return h, float(total_fees)
        except Exception as exc:
            logger.warning("[WrappedGenerator] biggest_waste user=%s: %s", user_id, exc)
            return None, 0.0

    # ── worst_fee ────────────────────────────────────────────────────

    def _worst_fee(self, user_id: str, year: int) -> Optional[WrappedHighlight]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT bank_name, fee_type, MAX(amount) as max_amount "
                        "FROM bank_fee_history "
                        "WHERE user_id = :uid AND month BETWEEN :m1 AND :m2 "
                        "GROUP BY bank_name, fee_type ORDER BY max_amount DESC LIMIT 1"
                    ),
                    {"uid": user_id, "m1": f"{year}-01", "m2": f"{year}-12"},
                ).fetchone()

            if not row:
                return None

            bank, fee_type, amount = row
            return WrappedHighlight(
                category="worst_fee",
                title="Tarifa mais absurda",
                value_formatted=f"{brl(float(amount))}",
                description=(
                    f"{_friendly_fee(fee_type)} do {bank}: "
                    f"{brl(float(amount))} em um único mês. "
                    "Use o Negociador Nexa para contestar ou migrar de banco."
                ),
            )
        except Exception as exc:
            logger.warning("[WrappedGenerator] worst_fee user=%s: %s", user_id, exc)
            return None

    # ── best_card_missed ─────────────────────────────────────────────

    def _best_card_missed(self, user_id: str) -> tuple[Optional[WrappedHighlight], float]:
        try:
            from app.optimizer.queries import get_optimization_reports

            reports = get_optimization_reports(user_id)
            if not reports:
                return None, 0.0

            latest = reports[-1]
            best = latest.get("best_card") or {}
            gain = float(best.get("net_gain_expected") or 0)
            card_name = best.get("card_name") or "cartão recomendado"

            if gain < 50:
                return None, 0.0

            h = WrappedHighlight(
                category="best_card_missed",
                title="Cartão que mais renderia",
                value_formatted=f"{brl(gain)}/ano",
                description=(
                    f"O {card_name} poderia ter te dado {brl(gain)} extras em {date.today().year} "
                    f"em pontos e cashback. Troque no app."
                ),
            )
            return h, gain
        except Exception as exc:
            logger.warning("[WrappedGenerator] best_card_missed user=%s: %s", user_id, exc)
            return None, 0.0

    # ── idle_money ───────────────────────────────────────────────────

    def _idle_money(self, user_id: str) -> tuple[Optional[WrappedHighlight], float]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT monthly_loss, top_opportunity "
                        "FROM opportunity_snapshots "
                        "WHERE user_id = :uid ORDER BY captured_at DESC LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()

            if not row or not row[0] or float(row[0]) <= 0:
                return None, 0.0

            monthly_loss = float(row[0])
            annual_loss = round(monthly_loss * 12, 2)
            bank = row[1] or "um banco de alta rentabilidade"

            h = WrappedHighlight(
                category="idle_money",
                title="Oportunidade que ficou na conta",
                value_formatted=f"{brl(annual_loss)}/ano",
                description=(
                    f"Você deixou {brl(monthly_loss)}/mês parado na conta corrente rendendo zero. "
                    f"Aplicado em {bank}, teria rendido {brl(annual_loss)} no ano."
                ),
            )
            return h, annual_loss
        except Exception as exc:
            logger.warning("[WrappedGenerator] idle_money user=%s: %s", user_id, exc)
            return None, 0.0

    # ── score_evolution ──────────────────────────────────────────────

    def _score_evolution(
        self, user_id: str, year: int
    ) -> tuple[Optional[WrappedHighlight], Optional[int], Optional[int]]:
        try:
            from app.core.database import SessionLocal
            from app.health_score.models import HealthScoreHistory
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT health_score, date FROM health_score_history "
                        "WHERE user_id = :uid "
                        "  AND EXTRACT(YEAR FROM date) = :year "
                        "ORDER BY date ASC"
                    ),
                    {"uid": user_id, "year": year},
                ).fetchall()

            if len(rows) < 2:
                return None, None, None

            score_start = int(rows[0][0])
            score_end = int(rows[-1][0])
            delta = score_end - score_start

            direction = "subiu" if delta >= 0 else "caiu"
            emoji_hint = "crescimento" if delta >= 0 else "queda"

            h = WrappedHighlight(
                category="score_evolution",
                title=f"Sua saúde financeira {direction}",
                value_formatted=f"{score_start} → {score_end} ({'+' if delta >= 0 else ''}{delta} pts)",
                description=(
                    f"Seu Health Score {direction} {abs(delta)} pontos em {year}: "
                    f"de {score_start} para {score_end}. "
                    + (
                        "Continue assim — você está no caminho certo!"
                        if delta >= 0 else
                        "Use as recomendações Nexa para recuperar o score em " + str(year + 1) + "."
                    )
                ),
            )
            return h, score_start, score_end
        except Exception as exc:
            logger.warning("[WrappedGenerator] score_evolution user=%s: %s", user_id, exc)
            return None, None, None

    # ── badges ───────────────────────────────────────────────────────

    def _get_badges(self, user_id: str, year: int) -> list[str]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT badge_type FROM user_badges "
                        "WHERE user_id = :uid "
                        "  AND EXTRACT(YEAR FROM earned_at) = :year "
                        "ORDER BY earned_at"
                    ),
                    {"uid": user_id, "year": year},
                ).fetchall()

            return [r[0] for r in rows]
        except Exception as exc:
            logger.warning("[WrappedGenerator] badges user=%s: %s", user_id, exc)
            return []

    # ── tagline ──────────────────────────────────────────────────────

    @staticmethod
    def _build_tagline(
        total_fees: float,
        total_savings: float,
        score_delta: Optional[int],
        badges: list[str],
        year: int,
    ) -> str:
        parts = []
        if total_fees > 0:
            parts.append(
                f"Você pagou {brl(total_fees)} em tarifas bancárias cobradas em {year}."
            )
        if total_savings > 0:
            parts.append(
                f"A Nexa identificou até {brl(total_savings)} em oportunidades potenciais — "
                "valores estimados, sujeitos a condições de mercado."
            )
        if score_delta is not None:
            verb = "cresceu" if score_delta >= 0 else "caiu"
            parts.append(f"Sua saúde financeira {verb} {abs(score_delta)} pontos.")
        if badges:
            parts.append(f"Conquistas em {year}: {', '.join(badges)}.")
        if not parts:
            return f"Seu resumo financeiro de {year} está pronto. Continue evoluindo com a Nexa."
        return " ".join(parts)


def _friendly_fee(fee_type: str) -> str:
    names = {
        "ANUIDADE": "anuidade do cartão",
        "TARIFA_MANUTENCAO": "manutenção de conta",
        "TARIFA_SAQUE": "saques",
        "TARIFA_TED": "TEDs",
        "TARIFA_DOC": "DOCs",
        "TARIFA_CADASTRO": "tarifa de cadastro",
        "SEGURO_EMBUTIDO": "seguros embutidos",
        "SEGURO_PRESTAMISTA": "seguro prestamista",
        "TAXA_JUROS": "juros",
    }
    return names.get(fee_type, fee_type.replace("_", " ").lower())


def _now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
