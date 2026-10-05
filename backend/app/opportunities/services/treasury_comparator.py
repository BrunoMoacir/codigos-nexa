"""
app/opportunities/services/treasury_comparator.py

OPP.3 (docs/ROADMAP.md) — Comparação Tesouro SELIC vs. CDB vs. poupança.

As três alternativas clássicas de "onde deixar a reserva", comparadas em
rendimento LÍQUIDO real para um valor e prazo informados:

  • Tesouro SELIC — IR regressivo + custódia B3 (IRPFCalculator.calc_ir_on_tesouro_selic)
  • Melhor CDB de liquidez diária do catálogo — IR regressivo
  • Poupança — isenta, taxa oficial via calculate_savings_rate (SELIC + TR)

Não depende de dados do usuário — mesma resposta para qualquer usuário num
dado dia. Conectores instanciados uma vez no __init__ (cache por instância
do BaseConnector; ver nota em SavingsVsCdiService).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.opportunities.models import (
    TreasuryComparisonEntry,
    TreasuryComparisonResponse,
)
from app.opportunities.services.savings_rate import calculate_savings_rate
from app.core.formatacao import brl

logger = logging.getLogger(__name__)

_DEFAULT_CDI_ANNUAL = 0.1465
_DEFAULT_SELIC_ANNUAL = 0.15


class TreasuryComparatorService:
    """Comparação a três (OPP.3), com taxas reais e fallback dos conectores."""

    def __init__(self, comparator=None) -> None:
        from app.architect.connectors.anbima import AnbimaConnector
        from app.architect.connectors.bacen import BacenConnector
        from app.opportunities.services.bank_comparator import BankComparator

        self._anbima = AnbimaConnector()
        self._bacen = BacenConnector()
        self._comparator = comparator or BankComparator()

    def compare(
        self,
        amount: float,
        holding_months: int = 12,
        disclaimer: str = "",
    ) -> TreasuryComparisonResponse:
        from app.fiscal.ir_pf_calculator import IRPFCalculator

        cdi_annual, selic_annual, tr_monthly = self._get_rates()
        savings = calculate_savings_rate(selic_annual, tr_monthly)
        ir_calc = IRPFCalculator()

        entries: list[TreasuryComparisonEntry] = []

        # 1. Tesouro SELIC (IR + custódia B3)
        tesouro = ir_calc.calc_ir_on_tesouro_selic(
            principal=amount,
            selic_annual=selic_annual,
            holding_months=holding_months,
        )
        gross_tesouro = amount * ((1 + selic_annual) ** (holding_months / 12) - 1)
        entries.append(TreasuryComparisonEntry(
            label="Tesouro SELIC",
            investment_type="TESOURO_SELIC",
            annual_rate_gross_pct=round(selic_annual * 100, 4),
            annual_rate_net_pct=tesouro.net_annual_rate_pct,
            net_yield_brl=tesouro.net_yield_brl,
            ir_rate=tesouro.ir_rate,
            is_exempt=False,
            fees_brl=round(gross_tesouro - tesouro.ir_brl - tesouro.net_yield_brl, 2),
            fgc_covered=False,
            liquidity="daily",
        ))

        # 2. Melhor CDB de liquidez diária do catálogo
        best_cdb = self._best_daily_cdb(amount, holding_months, cdi_annual)
        if best_cdb is not None:
            entries.append(best_cdb)

        # 3. Poupança (isenta)
        savings_result = ir_calc.calc_ir_on_lci_lca(
            principal=amount,
            annual_rate_pct=savings.savings_annual * 100,
            holding_months=holding_months,
            investment_type="POUPANCA",
        )
        savings_entry = TreasuryComparisonEntry(
            label="Poupança",
            investment_type="POUPANCA",
            annual_rate_gross_pct=round(savings.savings_annual * 100, 4),
            annual_rate_net_pct=savings_result.net_annual_rate_pct,
            net_yield_brl=savings_result.net_yield_brl,
            ir_rate=0.0,
            is_exempt=True,
            fgc_covered=True,
            liquidity="daily",
        )
        entries.append(savings_entry)

        entries.sort(key=lambda e: -e.net_yield_brl)
        winner = entries[0]

        return TreasuryComparisonResponse(
            amount=amount,
            holding_months=holding_months,
            selic_annual_pct=round(selic_annual * 100, 4),
            cdi_annual_pct=round(cdi_annual * 100, 4),
            savings_annual_pct=round(savings.savings_annual * 100, 4),
            entries=entries,
            winner=winner.label,
            winner_vs_savings_brl=round(winner.net_yield_brl - savings_entry.net_yield_brl, 2),
            recommendation=self._build_recommendation(
                amount, holding_months, winner, savings_entry
            ),
            disclaimer=disclaimer,
            generated_at=datetime.now(timezone.utc),
        )

    # ── helpers ──────────────────────────────────────────────────────

    def _get_rates(self) -> tuple[float, float, float]:
        try:
            cdi_annual = self._anbima.get_cdi()
        except Exception as exc:
            logger.warning("[TreasuryComparator] CDI fallback: %s", exc)
            cdi_annual = _DEFAULT_CDI_ANNUAL
        try:
            selic_annual = self._bacen.get_selic()
            tr_monthly = self._bacen.get_tr_monthly()
        except Exception as exc:
            logger.warning("[TreasuryComparator] SELIC/TR fallback: %s", exc)
            selic_annual, tr_monthly = _DEFAULT_SELIC_ANNUAL, 0.0
        return cdi_annual, selic_annual, tr_monthly

    def _best_daily_cdb(
        self, amount: float, holding_months: int, cdi_annual: float
    ) -> TreasuryComparisonEntry | None:
        """Melhor CDB elegível com liquidez diária do catálogo — comparação
        justa com Tesouro Selic/poupança, que também têm liquidez diária."""
        try:
            ranked = self._comparator.rank(
                amount=amount, holding_months=holding_months, cdi_annual=cdi_annual
            )
        except Exception as exc:
            logger.warning("[TreasuryComparator] rank falhou: %s", exc)
            return None

        best = next(
            (i for i in ranked
             if i.product_type == "CDB" and i.liquidity_days <= 1 and i.eligible),
            None,
        )
        if best is None:
            return None

        return TreasuryComparisonEntry(
            label=f"CDB {best.bank_name} {best.cdi_pct:.0f}% CDI",
            investment_type="CDB",
            annual_rate_gross_pct=best.annual_rate_gross_pct,
            annual_rate_net_pct=best.annual_rate_net_pct,
            net_yield_brl=best.annual_gain_brl,
            ir_rate=best.ir_rate,
            is_exempt=False,
            fgc_covered=best.fgc_covered,
            liquidity=best.liquidity,
        )

    @staticmethod
    def _build_recommendation(
        amount: float,
        holding_months: int,
        winner: TreasuryComparisonEntry,
        savings: TreasuryComparisonEntry,
    ) -> str:
        if winner.investment_type == "POUPANCA":
            return (
                "Com as taxas atuais, a poupança empata ou supera as alternativas "
                "nesta simulação — situação incomum; vale reconferir as taxas."
            )
        diff = winner.net_yield_brl - savings.net_yield_brl
        guarantee = (
            "garantia do Tesouro Nacional"
            if winner.investment_type == "TESOURO_SELIC"
            else "garantia FGC até R$ 250 mil"
        )
        return (
            f"Para {brl(amount)} por {holding_months} meses, {winner.label} rende "
            f"{brl(winner.net_yield_brl)} líquidos — {brl(diff)} a mais que a "
            f"poupança ({brl(savings.net_yield_brl)}), com liquidez diária e {guarantee}."
        )


__all__ = ["TreasuryComparatorService"]
