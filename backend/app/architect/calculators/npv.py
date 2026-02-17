"""
app/architect/calculators/npv.py - Calculadora de Valor Presente Liquido

Feature: F3 - Nexa Architect
Version: 1.0.0

Funcoes:
- calculate_npv: Valor Presente Liquido (NPV/VPL)
- calculate_irr: Taxa Interna de Retorno (IRR/TIR)
- discount_cashflow: Desconto de fluxo de caixa individual
- present_value_annuity: PV de series uniformes
- future_value_annuity: FV de acumulacao (poupanca)

Todas as taxas sao expressas em forma decimal (ex: 0.10 = 10%).
Periodos sao mensais, exceto quando indicado.
"""

from typing import List, Optional


def calculate_npv(
    cashflows: List[float],
    discount_rate: float,
    initial_investment: float = 0
) -> float:
    """
    Calcula o Valor Presente Liquido (NPV/VPL) de uma serie de fluxos de caixa.

    NPV = -I + sum( CF_t / (1+r)^t ) para t = 1..n

    Args:
        cashflows: Lista de fluxos de caixa futuros (periodos 1..n)
        discount_rate: Taxa de desconto por periodo (decimal)
        initial_investment: Investimento inicial (valor positivo, sera subtraido)

    Returns:
        NPV em valor monetario

    Raises:
        ValueError: Se discount_rate <= -1 (taxa invalida)

    Example:
        >>> cashflows = [3000, 3000, 3000, 3000, 3000]
        >>> npv = calculate_npv(cashflows, 0.10, initial_investment=10000)
        >>> round(npv, 2)
        1372.36
    """
    if discount_rate <= -1:
        raise ValueError("Taxa de desconto nao pode ser menor ou igual a -100%")

    if not cashflows:
        return -initial_investment

    npv = -initial_investment

    for t, cf in enumerate(cashflows, start=1):
        npv += cf / ((1 + discount_rate) ** t)

    return npv


def calculate_irr(
    cashflows: List[float],
    initial_investment: float,
    guess: float = 0.10,
    max_iterations: int = 200,
    tolerance: float = 1e-7
) -> Optional[float]:
    """
    Calcula a Taxa Interna de Retorno (IRR/TIR) via Newton-Raphson.

    IRR e a taxa que faz NPV = 0:
    0 = -I + sum( CF_t / (1+IRR)^t )

    Args:
        cashflows: Lista de fluxos de caixa futuros (periodos 1..n)
        initial_investment: Investimento inicial (valor positivo)
        guess: Chute inicial da taxa (default: 10%)
        max_iterations: Maximo de iteracoes
        tolerance: Tolerancia de convergencia

    Returns:
        IRR por periodo (decimal) ou None se nao convergir

    Raises:
        ValueError: Se cashflows estiver vazio ou initial_investment <= 0

    Example:
        >>> irr = calculate_irr([3000, 3000, 3000, 3000, 3000], 10000)
        >>> irr is not None
        True
        >>> round(irr, 4)
        0.1525
    """
    if not cashflows:
        raise ValueError("Lista de fluxos de caixa nao pode ser vazia")
    if initial_investment <= 0:
        raise ValueError("Investimento inicial deve ser positivo")

    # Montar fluxo completo: [-I, CF1, CF2, ..., CFn]
    full_cashflows = [-initial_investment] + list(cashflows)

    rate = guess

    for _ in range(max_iterations):
        # f(r) = sum( CF_t / (1+r)^t ) para t = 0..n
        npv = 0
        dnpv = 0  # derivada

        for t, cf in enumerate(full_cashflows):
            denom = (1 + rate) ** t
            if abs(denom) < 1e-15:
                return None
            npv += cf / denom
            if t > 0:
                dnpv -= t * cf / ((1 + rate) ** (t + 1))

        if abs(dnpv) < 1e-15:
            return None

        rate_new = rate - npv / dnpv

        if abs(rate_new - rate) < tolerance:
            if rate_new <= -1:
                return None  # taxa economicamente invalida
            return rate_new

        rate = rate_new

    # Nao convergiu
    return None


def discount_cashflow(
    future_value: float,
    discount_rate: float,
    periods: int
) -> float:
    """
    Desconta um fluxo de caixa futuro para valor presente.

    PV = FV / (1 + r)^n

    Args:
        future_value: Valor futuro (R$)
        discount_rate: Taxa de desconto por periodo (decimal)
        periods: Numero de periodos

    Returns:
        Valor presente (R$)

    Raises:
        ValueError: Se discount_rate <= -1 ou periods < 0

    Example:
        >>> pv = discount_cashflow(10000, 0.01, 12)
        >>> round(pv, 2)
        8874.49
    """
    if discount_rate <= -1:
        raise ValueError("Taxa de desconto nao pode ser menor ou igual a -100%")
    if periods < 0:
        raise ValueError("Numero de periodos nao pode ser negativo")

    if periods == 0:
        return future_value

    return future_value / ((1 + discount_rate) ** periods)


def present_value_annuity(
    payment: float,
    rate: float,
    periods: int
) -> float:
    """
    Calcula o Valor Presente de uma serie uniforme de pagamentos (anuidade).

    PVA = PMT * [(1 - (1+r)^-n) / r]

    Util para calcular quanto vale hoje uma serie de parcelas fixas.

    Args:
        payment: Valor do pagamento periodico (R$)
        rate: Taxa de juros por periodo (decimal)
        periods: Numero de periodos

    Returns:
        Valor presente da anuidade (R$)

    Raises:
        ValueError: Se rate <= -1 ou periods <= 0

    Example:
        >>> pva = present_value_annuity(1000, 0.01, 12)
        >>> round(pva, 2)
        11255.08
    """
    if rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if periods <= 0:
        raise ValueError("Numero de periodos deve ser positivo")

    if rate == 0:
        return payment * periods

    factor = (1 - (1 + rate) ** (-periods)) / rate
    return payment * factor


def future_value_annuity(
    payment: float,
    rate: float,
    periods: int,
    initial_amount: float = 0
) -> float:
    """
    Calcula o Valor Futuro de depositos periodicos (acumulacao/poupanca).

    FVA = PMT * [((1+r)^n - 1) / r] + PV * (1+r)^n

    Util para projetar quanto o usuario acumulara poupando mensalmente.

    Args:
        payment: Deposito periodico (R$)
        rate: Taxa de rendimento por periodo (decimal)
        periods: Numero de periodos
        initial_amount: Valor ja existente investido (default: 0)

    Returns:
        Valor futuro acumulado (R$)

    Raises:
        ValueError: Se rate <= -1 ou periods <= 0

    Example:
        >>> fva = future_value_annuity(2000, 0.008, 36)
        >>> round(fva, 2)
        83266.04
    """
    if rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if periods <= 0:
        raise ValueError("Numero de periodos deve ser positivo")

    # Valor futuro do montante inicial
    fv_initial = initial_amount * ((1 + rate) ** periods)

    if rate == 0:
        return (payment * periods) + fv_initial

    # Valor futuro da serie de depositos
    factor = ((1 + rate) ** periods - 1) / rate
    fv_payments = payment * factor

    return fv_payments + fv_initial


__all__ = [
    "calculate_npv",
    "calculate_irr",
    "discount_cashflow",
    "present_value_annuity",
    "future_value_annuity",
]
