"""
app/architect/calculators/financing.py - Calculadora de Financiamento

Feature: F3 - Nexa Architect
Version: 1.0.0

Sistemas de Amortizacao:
- PRICE: Parcelas fixas (System Francais)
- SAC: Amortizacao constante (System Americano)

Custos incluidos:
- Juros mensais
- IOF (0,38% padrao simplificado)
- Tarifas administrativas
"""

from typing import List, Dict
from dataclasses import dataclass, asdict


@dataclass
class FinancingResult:
    """
    Resultado completo de simulacao de financiamento.

    Attributes:
        monthly_payment: Valor da parcela (primeira, se SAC)
        total_paid: Total pago ao longo do financiamento
        total_interest: Total de juros pagos
        total_iof: Total de IOF
        admin_fee: Tarifa administrativa
        total_cost: Custo total (principal + juros + IOF + tarifas)
        schedule: Lista de dicts com detalhes de cada parcela
        cet_annual: Custo Efetivo Total anualizado
    """
    monthly_payment: float
    total_paid: float
    total_interest: float
    total_iof: float
    admin_fee: float
    total_cost: float
    schedule: List[Dict[str, float]]
    cet_annual: float

    def to_dict(self) -> Dict:
        """Converte para dict"""
        return asdict(self)


def calculate_price(
    principal: float,
    annual_rate: float,
    months: int,
    iof_rate: float = 0.0038,
    admin_fee: float = 0
) -> FinancingResult:
    """
    Calcula financiamento pelo sistema PRICE (parcelas fixas).

    No sistema PRICE, a parcela e constante durante todo o prazo.
    Inicialmente, a maior parte da parcela e juros; ao final, e amortizacao.

    Args:
        principal: Valor financiado (R$)
        annual_rate: Taxa de juros anual (decimal, ex: 0.12 = 12%)
        months: Prazo em meses
        iof_rate: Taxa de IOF sobre principal (default: 0.38%)
        admin_fee: Tarifa administrativa unica (R$)

    Returns:
        FinancingResult com todos os detalhes

    Formula PRICE:
        PMT = P * [r(1+r)^n / ((1+r)^n - 1)]
        onde:
        P = principal
        r = taxa mensal (capitalizacao composta: (1+i_a)^(1/12) - 1)
        n = numero de meses

    Example:
        >>> result = calculate_price(
        ...     principal=50000,
        ...     annual_rate=0.12,
        ...     months=48
        ... )
        >>> print(f"Parcela: R$ {result.monthly_payment:.2f}")
        Parcela: R$ 1.318,03
    """

    if principal <= 0:
        raise ValueError("Principal deve ser positivo")
    if annual_rate < 0:
        raise ValueError("Taxa nao pode ser negativa")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    # Converter taxa anual para mensal (capitalizacao composta)
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    # Calcular parcela PRICE
    if monthly_rate == 0:
        pmt = principal / months
    else:
        numerator = monthly_rate * (1 + monthly_rate) ** months
        denominator = (1 + monthly_rate) ** months - 1
        pmt = principal * (numerator / denominator)

    # Gerar tabela de amortizacao
    schedule = []
    balance = principal

    for month in range(1, months + 1):
        interest = balance * monthly_rate
        amortization = pmt - interest
        balance -= amortization

        if month == months:
            balance = 0

        schedule.append({
            "month": month,
            "payment": round(pmt, 2),
            "interest": round(interest, 2),
            "amortization": round(amortization, 2),
            "balance": round(max(0, balance), 2),
        })

    # Totais derivados do schedule (consistencia com arredondamento)
    total_interest = sum(row["interest"] for row in schedule)
    total_paid = sum(row["payment"] for row in schedule)

    # IOF e custos
    total_iof = round(principal * iof_rate, 2)
    total_cost = total_paid + total_iof + admin_fee

    # CET (Custo Efetivo Total)
    principal_liquido = principal - total_iof - admin_fee
    payments = [row["payment"] for row in schedule]
    cet_annual = _calculate_cet(principal_liquido, payments)

    return FinancingResult(
        monthly_payment=round(pmt, 2),
        total_paid=round(total_paid, 2),
        total_interest=round(total_interest, 2),
        total_iof=total_iof,
        admin_fee=admin_fee,
        total_cost=round(total_cost, 2),
        schedule=schedule,
        cet_annual=cet_annual,
    )


def calculate_sac(
    principal: float,
    annual_rate: float,
    months: int,
    iof_rate: float = 0.0038,
    admin_fee: float = 0
) -> FinancingResult:
    """
    Calcula financiamento pelo sistema SAC (amortizacao constante).

    No SAC, a amortizacao e constante. As parcelas sao decrescentes
    pois os juros diminuem conforme o saldo devedor cai.

    Args:
        principal: Valor financiado (R$)
        annual_rate: Taxa anual (decimal)
        months: Prazo em meses
        iof_rate: IOF (default: 0.38%)
        admin_fee: Tarifa (R$)

    Returns:
        FinancingResult

    Formula SAC:
        Amortizacao = P / n (constante)
        Juros_t = Saldo_t * r
        PMT_t = Amortizacao + Juros_t (decrescente)

    Example:
        >>> result = calculate_sac(
        ...     principal=50000,
        ...     annual_rate=0.12,
        ...     months=48
        ... )
        >>> # Primeira parcela: amort + juros = 1041.67 + 474.45 = 1516.12
        >>> # (taxa mensal composta: (1.12)^(1/12) - 1 = 0.9489%)
    """

    if principal <= 0:
        raise ValueError("Principal deve ser positivo")
    if annual_rate < 0:
        raise ValueError("Taxa nao pode ser negativa")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    # Taxa mensal (capitalizacao composta)
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    # Amortizacao constante
    amortization = principal / months

    # Gerar tabela
    schedule = []
    balance = principal

    for month in range(1, months + 1):
        interest = balance * monthly_rate
        payment = amortization + interest
        balance -= amortization

        if month == months:
            balance = 0

        schedule.append({
            "month": month,
            "payment": round(payment, 2),
            "interest": round(interest, 2),
            "amortization": round(amortization, 2),
            "balance": round(max(0, balance), 2),
        })

    # Totais derivados do schedule (consistencia com arredondamento)
    total_interest = sum(row["interest"] for row in schedule)
    total_paid = sum(row["payment"] for row in schedule)

    # IOF e custos
    total_iof = round(principal * iof_rate, 2)
    total_cost = total_paid + total_iof + admin_fee

    # CET
    principal_liquido = principal - total_iof - admin_fee
    payments = [row["payment"] for row in schedule]
    cet_annual = _calculate_cet(principal_liquido, payments)

    return FinancingResult(
        monthly_payment=round(schedule[0]["payment"], 2),
        total_paid=round(total_paid, 2),
        total_interest=round(total_interest, 2),
        total_iof=total_iof,
        admin_fee=admin_fee,
        total_cost=round(total_cost, 2),
        schedule=schedule,
        cet_annual=cet_annual,
    )


def _calculate_cet(
    principal_liquido: float,
    payments: List[float],
    max_iterations: int = 100
) -> float:
    """
    Calcula CET (Custo Efetivo Total) anualizado via Newton-Raphson.

    CET e a taxa mensal r que satisfaz:
        principal_liquido = sum( payment_t / (1+r)^t )

    Funciona tanto para PRICE (parcelas iguais) quanto SAC (parcelas variaveis).

    Args:
        principal_liquido: Principal - IOF - tarifas
        payments: Lista de parcelas mensais
        max_iterations: Max iteracoes

    Returns:
        CET anualizado (decimal)

    Raises:
        ValueError: Se principal_liquido <= 0
    """
    if principal_liquido <= 0:
        raise ValueError("Tarifas e IOF nao podem exceder o principal")

    # Chute inicial: 1% a.m.
    rate = 0.01

    for _ in range(max_iterations):
        # f(r) = VPL(parcelas) - principal_liquido
        npv = 0
        dnpv = 0

        for t, pmt in enumerate(payments, start=1):
            denom = (1 + rate) ** t
            npv += pmt / denom
            dnpv -= t * pmt / ((1 + rate) ** (t + 1))

        if abs(dnpv) < 1e-10:
            break

        rate_new = rate - (npv - principal_liquido) / dnpv

        if abs(rate_new - rate) < 1e-6:
            # Validar resultado final
            if rate_new <= 0:
                return 0.0
            return (1 + rate_new) ** 12 - 1

        rate = rate_new

    # Se nao convergir, retornar estimativa com o melhor rate obtido
    if rate <= 0:
        return 0.0
    return (1 + rate) ** 12 - 1


def compare_methods(
    principal: float,
    annual_rate: float,
    months: int
) -> Dict[str, FinancingResult]:
    """
    Compara PRICE vs SAC lado a lado.

    Args:
        principal: Valor financiado
        annual_rate: Taxa anual
        months: Prazo

    Returns:
        Dict com resultados de ambos os metodos

    Example:
        >>> comparison = compare_methods(50000, 0.12, 48)
        >>> comparison["SAC"].total_cost < comparison["PRICE"].total_cost
        True
    """

    price = calculate_price(principal, annual_rate, months)
    sac = calculate_sac(principal, annual_rate, months)

    return {
        "PRICE": price,
        "SAC": sac,
    }


__all__ = [
    "calculate_price",
    "calculate_sac",
    "compare_methods",
    "FinancingResult",
]
