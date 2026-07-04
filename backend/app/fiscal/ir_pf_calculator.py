"""
app/fiscal/ir_pf_calculator.py — IRPFCalculator (T1/T2)

Calcula IR de pessoa física sobre rendimentos de investimentos de renda fixa.

Tabela regressiva (Lei 8.981/1995, art. 65):
  Até 180 dias        → 22,5%
  181 a 360 dias      → 20,0%
  361 a 720 dias      → 17,5%
  Acima de 720 dias   → 15,0%

Isentos de IR (PF):
  LCI, LCA, CRI, CRA, Debentures incentivadas, Poupança.

IOF: incide nos primeiros 29 dias (regressivo de 96% → 0%).
     Não é calculado aqui porque o rendimento tributável já é líquido de IOF
     quando o banco emite o IR na fonte.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# ── Tabela regressiva de IR ──────────────────────────────────────────
# (prazo máximo inclusivo em dias, alíquota)
_IR_BANDS: list[tuple[int, float]] = [
    (180, 0.225),
    (360, 0.200),
    (720, 0.175),
    (math.inf, 0.150),  # type: ignore[arg-type]
]

InvestmentType = Literal[
    "CDB", "LCI", "LCA", "CRI", "CRA", "DEBENTURE_INCENTIVADA", "POUPANCA", "TESOURO_SELIC"
]

_EXEMPT: frozenset[str] = frozenset({"LCI", "LCA", "CRI", "CRA", "DEBENTURE_INCENTIVADA", "POUPANCA"})


# ── Resultado de comparação ───────────────────────────────────────────

@dataclass
class IRResult:
    investment_type: str
    gross_yield_brl: float        # rendimento bruto (R$)
    ir_rate: float                # alíquota efetiva (0.0–0.225)
    ir_brl: float                 # IR retido (R$)
    net_yield_brl: float          # rendimento líquido (R$)
    net_annual_rate_pct: float    # taxa líquida equivalente ao ano (%)
    is_exempt: bool


@dataclass
class BreakevenResult:
    cdb_gross_rate_pct: float       # taxa bruta do CDB informada (% a.a.)
    cdb_ir_rate: float              # alíquota IR aplicada
    cdb_net_rate_pct: float         # taxa líquida do CDB (% a.a.)
    lci_breakeven_pct: float        # taxa mínima de LCI equivalente (% a.a.)
    lci_advantage_pct: float | None # quanto a LCI informada supera o breakeven


@dataclass
class ComparisonResult:
    amount: float
    holding_months: int
    cdb: IRResult
    lci: IRResult
    recommended: str        # "CDB" | "LCI" — melhor rendimento líquido
    net_difference_brl: float   # diferença de rendimento líquido (LCI − CDB)


# ── Calculadora ───────────────────────────────────────────────────────

class IRPFCalculator:
    """
    Calculadora de IR sobre rendimentos de renda fixa para Pessoa Física.

    Uso básico:
        calc = IRPFCalculator()
        result = calc.calc_ir_on_cdb(principal=10_000, annual_rate_pct=12.5, holding_months=13)
        print(result.net_yield_brl)   # rendimento líquido em R$

    Comparação CDB vs LCI:
        comp = calc.compare(principal=50_000, cdb_rate_pct=13.0, lci_rate_pct=10.8, holding_months=24)
        print(comp.recommended)
    """

    # ── IR sobre CDB / Tesouro / fundos com come-cotas ──────────────

    def calc_ir_on_cdb(
        self,
        principal: float,
        annual_rate_pct: float,
        holding_months: int,
    ) -> IRResult:
        """
        Calcula IR regressivo sobre rendimento de CDB ou qualquer título tributado.

        Args:
            principal:        Valor aplicado (R$).
            annual_rate_pct:  Taxa bruta anual do CDB (%).
                              Ex: 12.5 para 12,5% a.a. ou 100% CDI quando CDI ≈ 12,5%.
            holding_months:   Prazo de aplicação em meses.

        Returns:
            IRResult com rendimento bruto, IR, rendimento líquido e taxa anual líquida.
        """
        holding_days = holding_months * 30  # aproximação convencional do mercado
        ir_rate = self._ir_rate(holding_days)

        # Rendimento bruto no período
        period_rate = (1 + annual_rate_pct / 100) ** (holding_months / 12) - 1
        gross_yield = principal * period_rate

        ir_brl = gross_yield * ir_rate
        net_yield = gross_yield - ir_brl

        # Taxa líquida equivalente ao ano
        net_period_rate = net_yield / principal
        net_annual_rate = ((1 + net_period_rate) ** (12 / max(holding_months, 1)) - 1) * 100

        return IRResult(
            investment_type="CDB",
            gross_yield_brl=round(gross_yield, 2),
            ir_rate=ir_rate,
            ir_brl=round(ir_brl, 2),
            net_yield_brl=round(net_yield, 2),
            net_annual_rate_pct=round(net_annual_rate, 4),
            is_exempt=False,
        )

    # ── IR sobre LCI / LCA / isentos ────────────────────────────────

    def calc_ir_on_lci_lca(
        self,
        principal: float,
        annual_rate_pct: float,
        holding_months: int,
        investment_type: InvestmentType = "LCI",
    ) -> IRResult:
        """
        Calcula rendimento de LCI/LCA ou outros títulos isentos de IR para PF.

        A taxa passada já é a taxa líquida (não há IR a reter).

        Args:
            principal:        Valor aplicado (R$).
            annual_rate_pct:  Taxa anual do papel (%).
            holding_months:   Prazo em meses.
            investment_type:  "LCI" | "LCA" | "CRI" | "CRA" | "DEBENTURE_INCENTIVADA" | "POUPANCA".

        Returns:
            IRResult com IR = 0 e rendimento líquido = bruto.
        """
        period_rate = (1 + annual_rate_pct / 100) ** (holding_months / 12) - 1
        gross_yield = principal * period_rate

        net_annual_rate = ((1 + gross_yield / principal) ** (12 / max(holding_months, 1)) - 1) * 100

        return IRResult(
            investment_type=investment_type,
            gross_yield_brl=round(gross_yield, 2),
            ir_rate=0.0,
            ir_brl=0.0,
            net_yield_brl=round(gross_yield, 2),
            net_annual_rate_pct=round(net_annual_rate, 4),
            is_exempt=True,
        )

    # ── Tesouro SELIC (IR regressivo + custódia B3) ──────────────────

    def calc_ir_on_tesouro_selic(
        self,
        principal: float,
        selic_annual: float,
        holding_months: int,
        custody_fee_annual: float = 0.0020,
        custody_exempt_limit: float = 10_000.0,
    ) -> IRResult:
        """
        Calcula rendimento líquido de Tesouro SELIC: IR regressivo (mesma
        tabela do CDB) + taxa de custódia B3 (0,20% a.a.) sobre o valor que
        exceder R$ 10.000 (isenção vigente para Tesouro Selic desde 2020).

        A custódia incide sobre o estoque (principal + rendimento) excedente,
        aproximada aqui sobre o valor médio do período — convenção
        conservadora e suficiente para comparação de oportunidades.

        Args:
            principal:            Valor aplicado (R$).
            selic_annual:         Taxa SELIC anual em decimal (ex: 0.15 = 15% a.a.).
            holding_months:       Prazo de aplicação em meses.
            custody_fee_annual:   Taxa de custódia B3 anual (decimal, padrão 0,20%).
            custody_exempt_limit: Estoque isento de custódia (R$, padrão 10k).

        Returns:
            IRResult com investment_type="TESOURO_SELIC"; a custódia é
            descontada do rendimento antes do cálculo da taxa líquida.
        """
        holding_days = holding_months * 30
        ir_rate = self._ir_rate(holding_days)
        years = holding_months / 12

        period_rate = (1 + selic_annual) ** years - 1
        gross_yield = principal * period_rate

        # Custódia B3 sobre o estoque médio excedente ao limite isento
        avg_position = principal + gross_yield / 2
        custody_base = max(avg_position - custody_exempt_limit, 0.0)
        custody_fee_brl = custody_base * custody_fee_annual * years

        taxable_yield = max(gross_yield - custody_fee_brl, 0.0)
        ir_brl = taxable_yield * ir_rate
        net_yield = gross_yield - custody_fee_brl - ir_brl

        net_period_rate = net_yield / principal
        net_annual_rate = ((1 + net_period_rate) ** (12 / max(holding_months, 1)) - 1) * 100

        return IRResult(
            investment_type="TESOURO_SELIC",
            gross_yield_brl=round(gross_yield, 2),
            ir_rate=ir_rate,
            ir_brl=round(ir_brl, 2),
            net_yield_brl=round(net_yield, 2),
            net_annual_rate_pct=round(net_annual_rate, 4),
            is_exempt=False,
        )

    # ── Breakeven LCI ────────────────────────────────────────────────

    def calc_breakeven_lci(
        self,
        cdb_gross_rate_pct: float,
        holding_months: int,
        lci_offered_rate_pct: float | None = None,
    ) -> BreakevenResult:
        """
        Calcula a taxa mínima de LCI/LCA que supera um CDB de mesma taxa bruta.

        Fórmula: lci_breakeven = cdb_rate * (1 − IR)
        Porque LCI rende 100% de sua taxa sem IR, enquanto CDB perde o IR.

        Args:
            cdb_gross_rate_pct:    Taxa bruta anual do CDB (%).
            holding_months:        Prazo em meses (determina a alíquota IR do CDB).
            lci_offered_rate_pct:  Taxa da LCI disponível no mercado (% a.a.), se souber.
                                   Usado apenas para calcular lci_advantage_pct.

        Returns:
            BreakevenResult com taxa breakeven e vantagem da LCI informada (se passada).
        """
        holding_days = holding_months * 30
        ir_rate = self._ir_rate(holding_days)

        cdb_net_rate = cdb_gross_rate_pct * (1 - ir_rate)
        lci_breakeven = cdb_net_rate  # LCI precisa apenas superar essa taxa para ser melhor

        advantage = None
        if lci_offered_rate_pct is not None:
            advantage = round(lci_offered_rate_pct - lci_breakeven, 4)

        return BreakevenResult(
            cdb_gross_rate_pct=round(cdb_gross_rate_pct, 4),
            cdb_ir_rate=ir_rate,
            cdb_net_rate_pct=round(cdb_net_rate, 4),
            lci_breakeven_pct=round(lci_breakeven, 4),
            lci_advantage_pct=round(advantage, 4) if advantage is not None else None,
        )

    # ── Comparação direta CDB vs LCI ─────────────────────────────────

    def compare(
        self,
        principal: float,
        cdb_rate_pct: float,
        lci_rate_pct: float,
        holding_months: int,
    ) -> ComparisonResult:
        """
        Compara rendimento líquido de CDB vs LCI para o mesmo capital e prazo.

        Args:
            principal:        Valor aplicado (R$).
            cdb_rate_pct:     Taxa bruta anual do CDB (%).
            lci_rate_pct:     Taxa anual da LCI (%, já líquida por ser isenta).
            holding_months:   Prazo em meses.

        Returns:
            ComparisonResult com rendimentos líquidos e recomendação.
        """
        cdb_result = self.calc_ir_on_cdb(principal, cdb_rate_pct, holding_months)
        lci_result = self.calc_ir_on_lci_lca(principal, lci_rate_pct, holding_months)

        net_diff = lci_result.net_yield_brl - cdb_result.net_yield_brl
        recommended = "LCI" if net_diff >= 0 else "CDB"

        return ComparisonResult(
            amount=principal,
            holding_months=holding_months,
            cdb=cdb_result,
            lci=lci_result,
            recommended=recommended,
            net_difference_brl=round(net_diff, 2),
        )

    # ── Helper privado ───────────────────────────────────────────────

    @staticmethod
    def _ir_rate(holding_days: int) -> float:
        """Retorna a alíquota IR regressiva com base no prazo em dias."""
        for max_days, rate in _IR_BANDS:
            if holding_days <= max_days:
                return rate
        return 0.15  # fallback (nunca atingido com a tabela acima)


__all__ = [
    "IRPFCalculator",
    "IRResult",
    "BreakevenResult",
    "ComparisonResult",
    "InvestmentType",
]
