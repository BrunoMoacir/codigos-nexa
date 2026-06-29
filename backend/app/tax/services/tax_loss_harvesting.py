"""
app/tax/services/tax_loss_harvesting.py — T1: Tax-Loss Harvesting

Identifica duas oportunidades de redução fiscal:

1. **Harvest loss** — posições com perda não realizada que podem ser resgatadas
   para abater ganhos tributáveis de outras posições.
   Regra: perda abate ganhos na mesma categoria (renda fixa vs. variável — separados).

2. **Hold longer** — posições tributáveis com prazo inferior a 180 dias ainda na
   faixa de 22,5% (a alíquota cai para 20% após 180 dias, 17,5% após 360 e 15% após 720).
   Segurar até o próximo bracket reduz IR sem precisar resgatar.
"""

from __future__ import annotations

import logging
from datetime import date

from app.tax.models import InvestmentPosition, TaxOpportunity
from app.tax.services.ir_calculator import ir_rate_for_months

logger = logging.getLogger(__name__)

# Brackets de IR (dias → alíquota; usamos meses para comparação)
_BRACKETS = [
    (6, 0.225),    # ≤ 180 dias
    (12, 0.200),   # 181-360 dias
    (24, 0.175),   # 361-720 dias
    (9999, 0.150), # > 720 dias
]


class TaxLossHarvester:
    """
    Identifica oportunidades de tax-loss harvesting e hold-longer na carteira.
    """

    def find_opportunities(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        opportunities: list[TaxOpportunity] = []
        opportunities.extend(self._find_harvest_loss(positions))
        opportunities.extend(self._find_hold_longer(positions))
        return opportunities

    # ── Harvest loss ─────────────────────────────────────────────────

    def _find_harvest_loss(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []

        losses = [p for p in positions if p.unrealized_gain < 0 and not p.is_exempt]
        gains_ir = sum(
            p.estimated_ir for p in positions if p.unrealized_gain > 0 and not p.is_exempt
        )

        if not losses or gains_ir <= 0:
            return results

        total_loss = abs(sum(p.unrealized_gain for p in losses))
        effective_offset = min(total_loss, sum(p.unrealized_gain for p in positions if p.unrealized_gain > 0))
        # IR economizado = offset × alíquota média das posições com ganho
        avg_rate = ir_rate_for_months(
            int(sum(p.holding_months for p in positions if p.unrealized_gain > 0) / max(1, len([p for p in positions if p.unrealized_gain > 0])))
        )
        tax_saving = round(effective_offset * avg_rate, 2)

        for pos in losses:
            loss_brl = abs(pos.unrealized_gain)
            saving_share = round(tax_saving * (loss_brl / total_loss), 2) if total_loss > 0 else 0.0
            results.append(
                TaxOpportunity(
                    opportunity_type="harvest_loss",
                    title=f"Colheita de perda — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Posição com perda não realizada de R$ {loss_brl:,.2f}. "
                        f"Resgatar e reinvestir permite abater esse valor de ganhos tributáveis, "
                        f"economizando aproximadamente R$ {saving_share:,.2f} em IR."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Resgatar a posição (perda de R$ {loss_brl:,.2f}), "
                        "registrar a perda e reinvestir em ativo equivalente. "
                        "A perda abate ganhos tributáveis do mesmo tipo no mesmo ano-calendário."
                    ),
                    estimated_tax_saving_brl=saving_share,
                    confidence="medium",
                )
            )

        return results

    # ── Hold longer ──────────────────────────────────────────────────

    def _find_hold_longer(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []

        for pos in positions:
            if pos.is_exempt or pos.annual_rate_pct == 0 or pos.unrealized_gain <= 0:
                continue

            current_rate = ir_rate_for_months(pos.holding_months)
            next_bracket_months, next_rate = self._next_bracket(pos.holding_months)
            if next_rate is None or next_rate >= current_rate:
                continue

            months_to_wait = next_bracket_months - pos.holding_months
            if months_to_wait <= 0 or months_to_wait > 6:
                continue

            ir_saving = round(pos.unrealized_gain * (current_rate - next_rate), 2)
            if ir_saving < 50:
                continue

            results.append(
                TaxOpportunity(
                    opportunity_type="hold_longer",
                    title=f"Aguardar bracket de IR — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Resgate atual: alíquota {current_rate*100:.0f}% de IR. "
                        f"Em {months_to_wait} mês(es) a alíquota cai para {next_rate*100:.0f}%. "
                        f"Economia estimada: R$ {ir_saving:,.2f} no resgate."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Aguardar {months_to_wait} mês(es) antes de resgatar para cair "
                        f"da faixa {current_rate*100:.0f}% → {next_rate*100:.0f}% de IR "
                        f"(economia de R$ {ir_saving:,.2f})."
                    ),
                    estimated_tax_saving_brl=ir_saving,
                    confidence="high",
                    action_deadline=f"Não resgatar nas próximas {months_to_wait * 4:.0f} semanas",
                )
            )

        return results

    @staticmethod
    def _next_bracket(holding_months: int) -> tuple[int, float | None]:
        for max_months, rate in _BRACKETS:
            if holding_months < max_months:
                return max_months, rate
        return 9999, None
