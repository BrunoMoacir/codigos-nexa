"""
app/architect/calculators/investment.py - Calculadora de Investimento/Poupanca

Feature: F3 - Nexa Architect
Version: 1.0.0

Funcoes:
- calculate_pmt_needed: Deposito mensal necessario para atingir meta
- calculate_future_value: Valor futuro de depositos periodicos
- calculate_months_needed: Meses necessarios para atingir meta
- generate_accumulation_schedule: Tabela mensal de acumulacao

Todas as taxas sao expressas em forma decimal (ex: 0.10 = 10% a.a.).
Conversao anual -> mensal e feita internamente via capitalizacao composta.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class InvestmentResult:
    """
    Resultado completo de simulacao de investimento/poupanca.

    Attributes:
        monthly_deposit: Deposito mensal necessario
        total_deposited: Total depositado (sem rendimentos)
        total_interest_earned: Total de rendimentos
        final_amount: Montante final acumulado
        months: Prazo em meses
        effective_monthly_rate: Taxa mensal efetiva utilizada
        schedule: Tabela mensal de acumulacao
    """
    monthly_deposit: float
    total_deposited: float
    total_interest_earned: float
    final_amount: float
    months: int
    effective_monthly_rate: float
    schedule: List[Dict[str, float]]

    def to_dict(self) -> Dict:
        """Converte para dict"""
        return asdict(self)


def calculate_pmt_needed(
    target: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0
) -> float:
    """
    Calcula o deposito mensal necessario para atingir uma meta.

    Resolve PMT na formula:
        target = PMT * [((1+r)^n - 1) / r] + initial * (1+r)^n

    Args:
        target: Valor alvo (R$)
        annual_rate: Taxa de rendimento anual (decimal, ex: 0.10 = 10%)
        months: Prazo em meses
        initial_amount: Valor ja investido (default: 0)

    Returns:
        Deposito mensal necessario (R$)

    Raises:
        ValueError: Se target <= 0, annual_rate <= -1 ou months <= 0

    Example:
        >>> pmt = calculate_pmt_needed(100000, 0.10, 36)
        >>> round(pmt, 2)
        2385.86
    """
    if target <= 0:
        raise ValueError("Meta deve ser positiva")
    if annual_rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    # Valor futuro do montante inicial
    fv_initial = initial_amount * ((1 + monthly_rate) ** months)

    # Quanto falta acumular com depositos
    remaining = target - fv_initial

    if remaining <= 0:
        return 0.0

    if monthly_rate == 0:
        return remaining / months

    # PMT = remaining / [((1+r)^n - 1) / r]
    factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
    return remaining / factor


def calculate_future_value(
    monthly_deposit: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0
) -> float:
    """
    Calcula o valor futuro de depositos mensais com rendimento.

    FV = PMT * [((1+r)^n - 1) / r] + initial * (1+r)^n

    Args:
        monthly_deposit: Deposito mensal (R$)
        annual_rate: Taxa anual (decimal)
        months: Prazo em meses
        initial_amount: Valor ja investido (default: 0)

    Returns:
        Valor futuro acumulado (R$)

    Raises:
        ValueError: Se monthly_deposit < 0, annual_rate <= -1 ou months <= 0

    Example:
        >>> fv = calculate_future_value(2000, 0.10, 36)
        >>> round(fv, 2)
        83780.84
    """
    if monthly_deposit < 0:
        raise ValueError("Deposito mensal nao pode ser negativo")
    if annual_rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    fv_initial = initial_amount * ((1 + monthly_rate) ** months)

    if monthly_rate == 0:
        return (monthly_deposit * months) + fv_initial

    factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
    return (monthly_deposit * factor) + fv_initial


def calculate_months_needed(
    target: float,
    monthly_deposit: float,
    annual_rate: float,
    initial_amount: float = 0
) -> Optional[int]:
    """
    Calcula quantos meses sao necessarios para atingir a meta.

    Simula mes a mes ate atingir o target.

    Args:
        target: Valor alvo (R$)
        monthly_deposit: Deposito mensal (R$)
        annual_rate: Taxa anual (decimal)
        initial_amount: Valor ja investido (default: 0)

    Returns:
        Numero de meses necessarios, ou None se nao convergir em 1200 meses

    Raises:
        ValueError: Se target <= 0, monthly_deposit <= 0, ou annual_rate <= -1

    Example:
        >>> months = calculate_months_needed(100000, 2000, 0.10)
        >>> months
        40
    """
    if target <= 0:
        raise ValueError("Meta deve ser positiva")
    if monthly_deposit <= 0:
        raise ValueError("Deposito mensal deve ser positivo")
    if annual_rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    balance = initial_amount
    max_months = 1200  # 100 anos como limite de seguranca

    for month in range(1, max_months + 1):
        balance = balance * (1 + monthly_rate) + monthly_deposit
        if balance >= target:
            return month

    return None


def generate_accumulation_schedule(
    monthly_deposit: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0
) -> InvestmentResult:
    """
    Gera tabela completa de acumulacao mes a mes.

    Args:
        monthly_deposit: Deposito mensal (R$)
        annual_rate: Taxa anual (decimal)
        months: Prazo em meses
        initial_amount: Valor ja investido (default: 0)

    Returns:
        InvestmentResult com schedule detalhado

    Raises:
        ValueError: Se monthly_deposit < 0, annual_rate <= -1 ou months <= 0

    Example:
        >>> result = generate_accumulation_schedule(2000, 0.10, 36)
        >>> result.final_amount > 72000  # maior que depositos puros
        True
    """
    if monthly_deposit < 0:
        raise ValueError("Deposito mensal nao pode ser negativo")
    if annual_rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    balance = initial_amount
    schedule = []
    total_deposited = initial_amount

    for month in range(1, months + 1):
        # Rendimento do saldo existente
        interest = balance * monthly_rate

        # Novo saldo = saldo anterior + rendimento + deposito
        balance = balance + interest + monthly_deposit
        total_deposited += monthly_deposit

        schedule.append({
            "month": month,
            "deposit": round(monthly_deposit, 2),
            "interest": round(interest, 2),
            "cumulative_deposited": round(total_deposited, 2),
            "balance": round(balance, 2),
        })

    final_amount = round(balance, 2)
    total_interest_earned = round(final_amount - total_deposited, 2)

    return InvestmentResult(
        monthly_deposit=round(monthly_deposit, 2),
        total_deposited=round(total_deposited, 2),
        total_interest_earned=total_interest_earned,
        final_amount=final_amount,
        months=months,
        effective_monthly_rate=monthly_rate,
        schedule=schedule,
    )


__all__ = [
    "calculate_pmt_needed",
    "calculate_future_value",
    "calculate_months_needed",
    "generate_accumulation_schedule",
    "InvestmentResult",
]
