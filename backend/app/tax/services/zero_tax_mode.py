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
from app.tax.parametros_fiscais import (
    BASE_LEGAL_COME_COTAS,
    COME_COTAS_ALIQUOTA_LONGO_PRAZO,
    proximo_come_cotas,
)
from app.tax.services.ir_calculator import calc_breakeven
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

#: O come-cotas seguinte, se o usuário trocar, é o que ele deixa de sofrer —
#: meio ano de diferimento garantido. Era 12 meses no cálculo antigo.
_MESES_DE_DIFERIMENTO = 6


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
            vantagem_ano = round(pos.amount * (advantage_pct / 100), 2)

            # Trocar exige RESGATAR o CDB, e o resgate paga IR sobre o ganho
            # acumulado na alíquota de hoje. Anunciar só a vantagem de taxa
            # ignora um custo conhecido e que já está calculado na posição —
            # numa posição com ganho grande ainda na faixa de 22,5%, a troca
            # pode ser negativa no primeiro ano.
            custo_resgate = round(pos.estimated_ir, 2)
            annual_saving = round(vantagem_ano - custo_resgate, 2)
            if annual_saving <= 0:
                continue

            results.append(
                TaxOpportunity(
                    opportunity_type="switch_to_lci",
                    title=f"CDB → LCI — {pos.bank_name} | {brl(pos.amount, 0)}",
                    description=(
                        f"CDB atual: {numero(pos.annual_rate_pct, 2)}% a.a. bruto → "
                        f"{numero(breakeven.cdb_net_rate_pct, 2)}% líquido após IR de {numero(breakeven.cdb_ir_rate * 100, 1)}%. "
                        f"Melhor LCI disponível: {best_lci['bank']} {numero(lci_rate, 2)}% a.a. (isento). "
                        f"Vantagem de {numero(advantage_pct, 2)} p.p. em relação ao breakeven."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Resgatar o CDB (atenção ao prazo de carência) e aplicar em "
                        f"LCI {best_lci['bank']} {numero(lci_rate, 2)}% a.a. "
                        f"Vantagem de taxa: {brl(vantagem_ano)}/ano (isento de IR). "
                        f"Menos o IR de {brl(custo_resgate)} devido no resgate do CDB, "
                        f"o ganho líquido no primeiro ano é de {brl(annual_saving)}."
                    ),
                    estimated_tax_saving_brl=annual_saving,
                    confidence="medium",
                )
            )

        return results


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

    # ── Come-cotas → CDB ─────────────────────────────────────────────

    def _find_come_cotas_switch(
        self, positions: list[InvestmentPosition], cdi_annual: float
    ) -> list[TaxOpportunity]:
        """
        Fundo com come-cotas → CDB.

        Três correções sobre a versão anterior:

        1. **O mês estava errado em sete dos doze meses do ano.** O rótulo
           saía de `meses_restantes <= 5 → "maio"`, e de junho a outubro a
           distância até novembro é ≤ 5 — então tudo virava "maio". A data
           impressa para maio era a string `"31/{ano}"`, sem mês: o usuário
           lia "Antes de 31/2026".
        2. **O benefício não é economia de imposto, é diferimento.** O IR sai
           no resgate de qualquer forma; o ganho é o rendimento do dinheiro
           que não foi antecipado. Vai marcado como `benefit_kind="deferral"`.
        3. **O horizonte era de 12 meses**, quando o que a troca garante é
           pular a próxima incidência — meio ano.
        """
        results: list[TaxOpportunity] = []
        today = date.today()
        data_come_cotas, nome_mes = proximo_come_cotas(today)
        dias_ate = max((data_come_cotas - today).days, 0)

        for pos in positions:
            if not pos.has_come_cotas or pos.amount <= 0 or pos.annual_rate_pct == 0:
                continue

            # Rendimento projetado até a próxima incidência
            period_rate = (1 + pos.annual_rate_pct / 100) ** (dias_ate / 365) - 1
            projected_gain = pos.current_balance * period_rate
            come_cotas_ir = round(projected_gain * COME_COTAS_ALIQUOTA_LONGO_PRAZO, 2)

            if come_cotas_ir < 100:
                continue

            # Quanto esse IR renderia se continuasse investido até a
            # incidência SEGUINTE, que é o que a troca garante adiar.
            ganho_diferimento = round(
                come_cotas_ir * ((1 + cdi_annual) ** (_MESES_DE_DIFERIMENTO / 12) - 1), 2
            )

            data_fmt = data_come_cotas.strftime("%d/%m/%Y")
            results.append(
                TaxOpportunity(
                    opportunity_type="avoid_come_cotas",
                    title=f"Evitar come-cotas — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Fundo com come-cotas: cerca de {brl(come_cotas_ir)} de IR "
                        f"serão antecipados em {data_fmt} ({nome_mes}). Migrar para CDB "
                        f"não elimina esse imposto — adia para o resgate. O ganho é o "
                        f"rendimento desse valor no meio-tempo: cerca de "
                        f"{brl(ganho_diferimento)} em {_MESES_DE_DIFERIMENTO} meses ao CDI."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Até {data_fmt}, avaliar o custo-benefício de migrar para CDB "
                        f"(sem come-cotas — IR só no resgate). Considere prazo restante, "
                        f"carência e o IR devido na saída do fundo. {BASE_LEGAL_COME_COTAS}"
                    ),
                    estimated_tax_saving_brl=ganho_diferimento,
                    benefit_kind="deferral",
                    confidence="low",
                    action_deadline=f"Até {data_fmt} ({nome_mes} — come-cotas)",
                )
            )

        return results
