"""Simulação segura para F9/F10.

Este módulo calcula cenários, mas não consulta instituições nem executa
portabilidade. A proposta real depende de análise de crédito e CET completos.
"""

from __future__ import annotations

from app.defense.models import (
    PortabilitySimulationRequest,
    PortabilitySimulationResponse,
)

_DISCLAIMER = (
    "Simulação educacional: não é proposta de crédito nem garantia de aprovação. "
    "Compare o CET, tarifas, seguros, prazo e condições da proposta real antes "
    "de solicitar portabilidade."
)


def _payment(balance: float, monthly_rate: float, months: int) -> float:
    factor = (1 + monthly_rate) ** months
    return balance * monthly_rate * factor / (factor - 1)


def simulate_portability(
    request: PortabilitySimulationRequest,
) -> PortabilitySimulationResponse:
    """Compara parcelas e custo total pelo sistema PRICE."""
    current_payment = request.current_payment or _payment(
        request.balance, request.current_monthly_rate, request.remaining_months
    )
    target_payment = _payment(
        request.balance, request.target_monthly_rate, request.remaining_months
    )
    current_total = current_payment * request.remaining_months
    target_total = target_payment * request.remaining_months
    savings = current_total - target_total

    if request.target_monthly_rate >= request.current_monthly_rate:
        status = "INVALID_TARGET"
        recommendation = (
            "A taxa proposta não é menor que a atual. Não há vantagem financeira "
            "nesta simulação; compare o CET antes de prosseguir."
        )
    elif savings > 0:
        status = "ADVANTAGEOUS"
        recommendation = (
            "A proposta reduz o custo estimado. Solicite o CET formal e confirme "
            "que não há tarifas, seguros ou alongamento de prazo escondidos."
        )
    else:
        status = "NO_ADVANTAGE"
        recommendation = (
            "A proposta não reduz o custo total estimado. Mantenha o contrato "
            "ou negocie melhores condições."
        )

    return PortabilitySimulationResponse(
        balance=round(request.balance, 2),
        remaining_months=request.remaining_months,
        current_monthly_rate=request.current_monthly_rate,
        target_monthly_rate=request.target_monthly_rate,
        current_payment=round(current_payment, 2),
        target_payment=round(target_payment, 2),
        current_total_cost=round(current_total, 2),
        target_total_cost=round(target_total, 2),
        estimated_savings=round(savings, 2),
        status=status,
        recommendation=recommendation,
        disclaimer=_DISCLAIMER,
    )


__all__ = ["simulate_portability"]
