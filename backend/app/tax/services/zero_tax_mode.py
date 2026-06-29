"""
app/tax/services/zero_tax_mode.py — T2: Modo Zero IR

Identifica duas oportunidades de eliminação ou diferimento de IR:

1. **CDB → LCI/LCA** — se houver LCI/LCA no mercado com taxa acima do breakeven
   (cdb_net_rate = cdb_rate × (1 − IR)), trocar elimina IR completamente.

2. **Fundo com come-cotas → CDB** — fundos RF/multimercado têm IR antecipado
   semestralmente (come-cotas em maio e novembro). Trocar por CDB difere o IR
   para o resgate, aumentando o capital que rende no período.

Usa `BankComparator` para verificar se há LCI/LCA disponível acima do breakeven.
"""

from __future__ import annotations

import logging
from datetime import date

from app.tax.models import InvestmentPosition, TaxOpportunity
from app.tax.services.ir_calculator import calc_breakeven

logger = logging.getLogger(__name__)

_COME_COTAS_MONTHS = [5, 11]  # maio e novembro
_COME_COTAS_IR_RATE = 0.15    # alíquota mínima aplicada no come-cotas


class ZeroTaxMode:
    """
    Identifica trocas de produto que eliminam ou diferem IR na carteira.
    """

    def find_opportunities(
        self, positions: list[InvestmentPosition], cdi_annual: float = 0.1465
    ) -> list[TaxOpportunity]:
        opportunities: list[TaxOpportunity] = []
        opportunities.extend(self._find_cdb_to_lci(positions, cdi_annual))
        opportunities.extend(self._find_come_cotas_switch(positions, cdi_annual))
        return opportunities

    # ── CDB → LCI/LCA ────────────────────────────────────────────────

    def _find_cdb_to_lci(
        self, positions: list[InvestmentPosition], cdi_annual: float
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []
        lci_options = self._get_lci_options(cdi_annual)

        for pos in positions:
            if pos.product_type != "CDB" or pos.annual_rate_pct == 0:
                continue

            breakeven = calc_breakeven(pos.annual_rate_pct, pos.holding_months)
            best_lci = max(lci_options, key=lambda x: x["rate_pct"], default=None)

            if not best_lci:
                continue

            lci_rate = best_lci["rate_pct"]
            if lci_rate <= breakeven.lci_breakeven_pct:
                continue

            advantage_pct = round(lci_rate - breakeven.lci_breakeven_pct, 4)
            annual_saving = round(pos.amount * (advantage_pct / 100), 2)

            results.append(
                TaxOpportunity(
                    opportunity_type="switch_to_lci",
                    title=f"CDB → LCI — {pos.bank_name} | R$ {pos.amount:,.0f}",
                    description=(
                        f"CDB atual: {pos.annual_rate_pct:.2f}% a.a. bruto → "
                        f"{breakeven.cdb_net_rate_pct:.2f}% líquido após IR {breakeven.cdb_ir_rate*100:.0f}%. "
                        f"Melhor LCI disponível: {best_lci['bank']} {lci_rate:.2f}% a.a. (isento). "
                        f"Vantagem de {advantage_pct:.2f} p.p. em relação ao breakeven."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Resgatar o CDB (atenção ao prazo de carência) e aplicar em "
                        f"LCI {best_lci['bank']} {lci_rate:.2f}% a.a. "
                        f"Ganho adicional estimado: R$ {annual_saving:,.2f}/ano (isento de IR)."
                    ),
                    estimated_tax_saving_brl=annual_saving,
                    confidence="medium",
                )
            )

        return results

    # ── Come-cotas → CDB ─────────────────────────────────────────────

    def _find_come_cotas_switch(
        self, positions: list[InvestmentPosition], cdi_annual: float
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []
        today = date.today()
        months_to_come_cotas = self._months_to_next_come_cotas(today)

        for pos in positions:
            if not pos.has_come_cotas or pos.amount <= 0 or pos.annual_rate_pct == 0:
                continue

            # IR antecipado no próximo come-cotas sobre o ganho estimado
            period_rate = (1 + pos.annual_rate_pct / 100) ** (months_to_come_cotas / 12) - 1
            projected_gain = pos.amount * period_rate
            come_cotas_ir = round(projected_gain * _COME_COTAS_IR_RATE, 2)

            if come_cotas_ir < 100:
                continue

            # Se esse IR ficasse aplicado mais 12 meses ao CDI, renderia:
            opportunity_cost = round(come_cotas_ir * cdi_annual, 2)

            deadline_month = "maio" if months_to_come_cotas <= 5 else "novembro"
            deadline_date = (
                f"31/{today.year}" if deadline_month == "maio" else f"30/11/{today.year}"
            )

            results.append(
                TaxOpportunity(
                    opportunity_type="avoid_come_cotas",
                    title=f"Evitar come-cotas — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Fundo com come-cotas: IR de ~R$ {come_cotas_ir:,.2f} será antecipado em {deadline_month}. "
                        f"Se esse valor permanecesse investido por 12 meses ao CDI, "
                        f"renderia mais R$ {opportunity_cost:,.2f}."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Antes de {deadline_date}, avaliar o custo-benefício de migrar para CDB "
                        f"(sem come-cotas — IR só no resgate). "
                        "Considere: prazo restante do fundo, carência e tributação da saída."
                    ),
                    estimated_tax_saving_brl=opportunity_cost,
                    confidence="low",
                    action_deadline=f"Antes de {deadline_date} ({deadline_month} — come-cotas)",
                )
            )

        return results

    # ── helpers ──────────────────────────────────────────────────────

    def _get_lci_options(self, cdi_annual: float) -> list[dict]:
        try:
            from app.opportunities.services.bank_comparator import BankComparator

            items = BankComparator().rank(
                amount=1_000.0, holding_months=12, cdi_annual=cdi_annual
            )
            return [
                {"bank": item.bank_name, "rate_pct": item.annual_rate_gross_pct}
                for item in items
                if item.product_type in ("LCI", "LCA") and item.eligible
            ]
        except Exception as exc:
            logger.warning("[ZeroTaxMode] get_lci_options: %s", exc)
            return []

    @staticmethod
    def _months_to_next_come_cotas(today: date) -> int:
        for month in sorted(_COME_COTAS_MONTHS):
            if today.month < month:
                return month - today.month
        # próximo ano
        return (12 - today.month) + _COME_COTAS_MONTHS[0]
