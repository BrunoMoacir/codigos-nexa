"""
app/tax/services/ir_calculator.py

Camada de orquestração de IR sobre a carteira completa.
Delega cálculos individuais ao IRPFCalculator (fiscal/ir_pf_calculator.py).
"""

from __future__ import annotations

from app.fiscal.ir_pf_calculator import IRPFCalculator, BreakevenResult
from app.tax.models import InvestmentPosition

_calc = IRPFCalculator()


def calc_portfolio_ir(positions: list[InvestmentPosition]) -> float:
    """Soma o IR estimado de todas as posições tributáveis da carteira."""
    return round(sum(p.estimated_ir for p in positions if not p.is_exempt), 2)


def calc_position_ir(position: InvestmentPosition) -> float:
    """(Re)calcula IR de uma posição específica."""
    if position.is_exempt or position.annual_rate_pct == 0:
        return 0.0
    try:
        result = _calc.calc_ir_on_cdb(
            principal=position.amount,
            annual_rate_pct=position.annual_rate_pct,
            holding_months=max(position.holding_months, 1),
        )
        return result.ir_brl
    except Exception:
        return 0.0


def calc_breakeven(
    cdb_rate_pct: float,
    holding_months: int,
    lci_offered_rate_pct: float | None = None,
) -> BreakevenResult:
    """Calcula taxa mínima de LCI que supera um CDB no prazo informado."""
    return _calc.calc_breakeven_lci(
        cdb_gross_rate_pct=cdb_rate_pct,
        holding_months=holding_months,
        lci_offered_rate_pct=lci_offered_rate_pct,
    )


def ir_rate_for_months(holding_months: int) -> float:
    """Retorna a alíquota IR (0–0.225) para o prazo em meses."""
    return IRPFCalculator._ir_rate(holding_months * 30)
