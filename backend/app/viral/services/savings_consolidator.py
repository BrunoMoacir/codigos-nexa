"""
app/viral/services/savings_consolidator.py — V1: Consolidação de Economia

Agrega economia identificada por 4 módulos Nexa:

  F2 Optimizer   → best_card.net_gain_expected (último relatório do usuário)
  F5 Costs       → savings_opportunity (análise de tarifas bancárias)
  F13 Negotiator → SUM(potential_gain) de negociações não tentadas ainda
  OPP            → top_gain_brl × 12 (opportunity_snapshots mais recente)

Retorna lista de SavingsSource + total_annual_savings_brl.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.viral.models import SavingsSource

logger = logging.getLogger(__name__)


class SavingsConsolidator:
    def consolidate(self, user_id: str) -> tuple[list[SavingsSource], float]:
        """
        Retorna (sources, total_annual_savings_brl).
        Cada source tem annual_savings_brl ≥ 0; nunca propaga exceção.
        """
        sources: list[SavingsSource] = []

        sources.append(self._optimizer_saving(user_id))
        sources.append(self._costs_saving(user_id))
        sources.append(self._negotiator_saving(user_id))
        sources.append(self._opportunities_saving(user_id))

        sources = [s for s in sources if s.annual_savings_brl > 0]
        total = round(sum(s.annual_savings_brl for s in sources), 2)
        return sources, total

    # ── F2 Optimizer ────────────────────────────────────────────────

    def _optimizer_saving(self, user_id: str) -> SavingsSource:
        try:
            from app.optimizer.queries import get_optimization_reports

            reports = get_optimization_reports(user_id)
            if not reports:
                return _zero("optimizer", "Otimizador de Cartões")

            # Pega o mais recente
            latest = reports[-1]
            best = latest.get("best_card") or {}
            annual = float(best.get("net_gain_expected") or 0)

            return SavingsSource(
                name="Otimizador de Cartões",
                module="optimizer",
                annual_savings_brl=round(annual, 2),
                description=(
                    f"Cartão {best.get('card_name', 'recomendado')}: "
                    f"ganho líquido esperado de R$ {annual:,.2f}/ano em pontos e cashback."
                ) if annual > 0 else "Nenhum ganho identificado no último relatório.",
            )
        except Exception as exc:
            logger.warning("[SavingsConsolidator] optimizer user=%s: %s", user_id, exc)
            return _zero("optimizer", "Otimizador de Cartões")

    # ── F5 Costs ────────────────────────────────────────────────────

    def _costs_saving(self, user_id: str) -> SavingsSource:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return _zero("costs", "Raio-X de Tarifas Bancárias")

            report = BankFeeAnalyzer().analyze(df, user_id)
            annual = round(report.savings_opportunity * 12, 2)

            return SavingsSource(
                name="Raio-X de Tarifas Bancárias",
                module="costs",
                annual_savings_brl=annual,
                description=(
                    f"Tarifas desnecessárias identificadas: R$ {report.savings_opportunity:,.2f}/mês "
                    f"(R$ {annual:,.2f}/ano de economia potencial)."
                ) if annual > 0 else "Nenhuma tarifa excessiva detectada.",
            )
        except Exception as exc:
            logger.warning("[SavingsConsolidator] costs user=%s: %s", user_id, exc)
            return _zero("costs", "Raio-X de Tarifas Bancárias")

    # ── F13 Negotiator ───────────────────────────────────────────────

    def _negotiator_saving(self, user_id: str) -> SavingsSource:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT COALESCE(SUM(potential_gain), 0) "
                        "FROM negotiation_history "
                        "WHERE user_id = :uid "
                        "  AND (result_status IS NULL OR result_status != 'recusado')"
                    ),
                    {"uid": user_id},
                ).fetchone()

            total = float(row[0]) if row else 0.0

            return SavingsSource(
                name="Negociador",
                module="negotiator",
                annual_savings_brl=round(total, 2),
                description=(
                    f"Ganho potencial identificado em negociações com seus bancos: "
                    f"R$ {total:,.2f} (anuidades, juros e tarifas)."
                ) if total > 0 else "Nenhuma negociação pendente.",
            )
        except Exception as exc:
            logger.warning("[SavingsConsolidator] negotiator user=%s: %s", user_id, exc)
            return _zero("negotiator", "Negociador")

    # ── OPP (opportunity_snapshots) ──────────────────────────────────

    def _opportunities_saving(self, user_id: str) -> SavingsSource:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT top_gain_brl, top_opportunity "
                        "FROM opportunity_snapshots "
                        "WHERE user_id = :uid "
                        "ORDER BY captured_at DESC LIMIT 1"
                    ),
                    {"uid": user_id},
                ).fetchone()

            if not row or not row[0]:
                return _zero("opportunities", "Radar de Oportunidades")

            monthly_gain = float(row[0])
            annual = round(monthly_gain * 12, 2)
            bank = row[1] or "banco recomendado"

            return SavingsSource(
                name="Radar de Oportunidades",
                module="opportunities",
                annual_savings_brl=annual,
                description=(
                    f"Dinheiro parado na conta corrente poderia render "
                    f"R$ {monthly_gain:,.2f}/mês aplicado em {bank} "
                    f"(R$ {annual:,.2f}/ano)."
                ),
            )
        except Exception as exc:
            logger.warning("[SavingsConsolidator] opportunities user=%s: %s", user_id, exc)
            return _zero("opportunities", "Radar de Oportunidades")


def _zero(module: str, name: str) -> SavingsSource:
    return SavingsSource(name=name, module=module, annual_savings_brl=0.0, description="")
