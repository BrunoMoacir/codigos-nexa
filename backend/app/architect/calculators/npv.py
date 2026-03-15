"""
app/architect/calculators/npv.py - Calculadora de Valor Presente Liquido

Feature: F3 - Nexa Architect
Version: 2.0.0

Funcoes:
- calculate_npv: Valor Presente Liquido (NPV/VPL), com suporte a VPL real (Fisher)
- calculate_irr: Taxa Interna de Retorno (IRR/TIR) com múltiplos chutes e detecção
                 de múltiplas raízes (regra de Descartes)
- discount_cashflow: Atalho — desconto de fluxo único (caso especial de calculate_npv)
- present_value_annuity: Atalho — PV de série uniforme (caso especial de calculate_npv)
- future_value_annuity: FV de acumulação periódica (canônica; investment.py a usa como base)

Todas as taxas são expressas em forma decimal (ex: 0.10 = 10%).
Períodos são mensais, exceto quando indicado.
"""

from dataclasses import dataclass
from typing import List, Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Resultado da TIR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class IRRResult:
    """
    Resultado de calculate_irr com informação sobre multiplicidade de raízes.

    Attributes:
        irr: Taxa interna de retorno por período (decimal), ou None se não
             convergiu em nenhum dos chutes tentados.
        multiple_roots_possible: True quando o fluxo de caixa completo
             (incluindo -initial_investment no período 0) tem mais de uma
             mudança de sinal, indicando que pode existir mais de uma TIR
             que zera o VPL (regra de Descartes). O valor retornado em `irr`
             é a primeira raiz encontrada — pode não ser a economicamente
             relevante.

    Example:
        >>> res = calculate_irr([3000, 3000, 3000], initial_investment=8000)
        >>> res.irr is not None
        True
        >>> res.multiple_roots_possible  # fluxo simples → False
        False
    """
    irr: Optional[float]
    multiple_roots_possible: bool


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constantes internas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Chutes a tentar em sequência quando o guess principal falha
_IRR_FALLBACK_GUESSES: List[float] = [0.01, 0.10, 0.50, 1.0]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Funções públicas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_npv(
    cashflows: List[float],
    discount_rate: float,
    initial_investment: float = 0,
    inflation_rate: float = 0.0,
) -> float:
    """
    Calcula o Valor Presente Líquido (NPV/VPL) de uma série de fluxos de caixa.

    NPV = -I + sum( CF_t / (1+r_eff)^t ) para t = 1..n

    Quando `inflation_rate > 0`, usa a taxa de desconto real via equação de Fisher,
    permitindo comparar estratégias de prazos longos em poder de compra:

        r_real = (1 + r_nominal) / (1 + inflação) - 1

    Args:
        cashflows: Lista de fluxos de caixa futuros (períodos 1..n).
        discount_rate: Taxa de desconto nominal por período (decimal).
        initial_investment: Investimento inicial (valor positivo, será subtraído).
        inflation_rate: Inflação por período (decimal). Quando > 0, o desconto
            é feito em termos reais (Fisher). Default: 0 (cálculo nominal).

    Returns:
        NPV em valor monetário (nominal ou real dependendo de inflation_rate).

    Raises:
        ValueError: Se discount_rate <= -1 ou inflation_rate <= -1.

    Example:
        >>> cashflows = [3000, 3000, 3000, 3000, 3000]
        >>> npv = calculate_npv(cashflows, 0.10, initial_investment=10000)
        >>> round(npv, 2)
        1372.36

        # VPL real com inflação de 0,5%/mês:
        >>> npv_real = calculate_npv(cashflows, 0.10, 10000, inflation_rate=0.005)
        >>> npv_real < npv  # desconto mais forte → VPL menor
        True
    """
    if discount_rate <= -1:
        raise ValueError("Taxa de desconto nao pode ser menor ou igual a -100%")
    if inflation_rate <= -1:
        raise ValueError("Taxa de inflacao nao pode ser menor ou igual a -100%")

    # Taxa efetiva: real (Fisher) quando inflação fornecida, nominal caso contrário
    if inflation_rate > 0:
        effective_rate = (1 + discount_rate) / (1 + inflation_rate) - 1
    else:
        effective_rate = discount_rate

    if not cashflows:
        return -initial_investment

    npv = -initial_investment

    for t, cf in enumerate(cashflows, start=1):
        npv += cf / ((1 + effective_rate) ** t)

    return npv


def calculate_irr(
    cashflows: List[float],
    initial_investment: float,
    guess: float = 0.10,
    max_iterations: int = 200,
    tolerance: float = 1e-7,
) -> IRRResult:
    """
    Calcula a Taxa Interna de Retorno (IRR/TIR) via Newton-Raphson.

    IRR é a taxa que faz NPV = 0:
        0 = -I + sum( CF_t / (1+IRR)^t )

    Convergência robusta: tenta o `guess` fornecido primeiro; se não convergir,
    tenta automaticamente os chutes alternativos [0.01, 0.10, 0.50, 1.0].
    Custo máximo: 4 × max_iterations iterações (800 no default).

    Detecção de múltiplas raízes: aplica a regra de Descartes no fluxo completo
    [-I, CF1, ..., CFn]. Se houver mais de uma mudança de sinal, `irr` pode não
    ser a única TIR — o caller deve interpretar o resultado com cautela.

    Args:
        cashflows: Lista de fluxos de caixa futuros (períodos 1..n).
        initial_investment: Investimento inicial (valor positivo).
        guess: Chute inicial da taxa (default: 10%).
        max_iterations: Máximo de iterações por tentativa.
        tolerance: Tolerância de convergência.

    Returns:
        IRRResult com:
            irr: TIR por período ou None se nenhum chute convergiu.
            multiple_roots_possible: True se há mais de uma mudança de sinal
                no fluxo (pode existir mais de uma TIR).

    Raises:
        ValueError: Se cashflows estiver vazio ou initial_investment <= 0.

    Example:
        >>> res = calculate_irr([3000, 3000, 3000, 3000, 3000], 10000)
        >>> res.irr is not None
        True
        >>> round(res.irr, 4)
        0.1525
        >>> res.multiple_roots_possible
        False

        # Fluxo com múltiplas mudanças de sinal (refinanciamento no meio):
        >>> cashflows_misto = [500, 500, -8000, 600, 600, 600, 600, 600, 600]
        >>> res = calculate_irr(cashflows_misto, 1000)
        >>> res.multiple_roots_possible  # aviso: pode haver outra TIR
        True
    """
    if not cashflows:
        raise ValueError("Lista de fluxos de caixa nao pode ser vazia")
    if initial_investment <= 0:
        raise ValueError("Investimento inicial deve ser positivo")

    full_cashflows = [-initial_investment] + list(cashflows)

    # Detecta múltiplas raízes pela regra de Descartes
    multiple_roots = _count_sign_changes(full_cashflows) > 1

    # Tenta o chute principal primeiro, depois os fallbacks
    guesses_to_try = [guess] + [g for g in _IRR_FALLBACK_GUESSES if abs(g - guess) > 1e-9]

    for g in guesses_to_try:
        rate = _newton_raphson_irr(full_cashflows, g, max_iterations, tolerance)
        if rate is not None:
            return IRRResult(irr=rate, multiple_roots_possible=multiple_roots)

    return IRRResult(irr=None, multiple_roots_possible=multiple_roots)


def discount_cashflow(
    future_value: float,
    discount_rate: float,
    periods: int,
) -> float:
    """
    Desconta um fluxo de caixa futuro para valor presente.

    PV = FV / (1 + r)^n

    Nota: este é um atalho conveniente para
        calculate_npv([future_value], discount_rate, periods=periods).
    Para descontar múltiplos fluxos, use calculate_npv diretamente.

    Args:
        future_value: Valor futuro (R$).
        discount_rate: Taxa de desconto por período (decimal).
        periods: Número de períodos.

    Returns:
        Valor presente (R$).

    Raises:
        ValueError: Se discount_rate <= -1 ou periods < 0.

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
    periods: int,
) -> float:
    """
    Calcula o Valor Presente de uma série uniforme de pagamentos (anuidade).

    PVA = PMT * [(1 - (1+r)^-n) / r]

    Nota: este é um atalho para calculate_npv([payment]*periods, rate).
    Útil quando todos os fluxos são iguais (parcelas fixas de financiamento,
    aluguéis uniformes, etc.).

    Args:
        payment: Valor do pagamento periódico (R$).
        rate: Taxa de juros por período (decimal).
        periods: Número de períodos.

    Returns:
        Valor presente da anuidade (R$).

    Raises:
        ValueError: Se rate <= -1 ou periods <= 0.

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
    initial_amount: float = 0,
) -> float:
    """
    Calcula o Valor Futuro de depósitos periódicos (acumulação/poupança).

    FVA = PMT * [((1+r)^n - 1) / r] + PV * (1+r)^n

    Esta é a função canônica de acumulação periódica. A função
    `calculate_future_value` em investment.py usa a mesma fórmula com
    conversão de taxa anual → mensal internamente. Prefira esta quando
    a taxa já está na unidade do período.

    Args:
        payment: Depósito periódico (R$).
        rate: Taxa de rendimento por período (decimal).
        periods: Número de períodos.
        initial_amount: Valor já existente investido (default: 0).

    Returns:
        Valor futuro acumulado (R$).

    Raises:
        ValueError: Se rate <= -1 ou periods <= 0.

    Example:
        >>> fva = future_value_annuity(2000, 0.008, 36)
        >>> round(fva, 2)
        83057.46
    """
    if rate <= -1:
        raise ValueError("Taxa nao pode ser menor ou igual a -100%")
    if periods <= 0:
        raise ValueError("Numero de periodos deve ser positivo")

    fv_initial = initial_amount * ((1 + rate) ** periods)

    if rate == 0:
        return (payment * periods) + fv_initial

    factor = ((1 + rate) ** periods - 1) / rate
    fv_payments = payment * factor

    return fv_payments + fv_initial


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers privados
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _count_sign_changes(cashflows: List[float]) -> int:
    """
    Conta mudanças de sinal consecutivas em uma série, ignorando zeros.

    Implementa a regra de Descartes: o número de raízes reais positivas
    de um polinômio é no máximo igual ao número de mudanças de sinal de
    seus coeficientes.
    """
    changes = 0
    last_sign = 0
    for cf in cashflows:
        if cf > 0:
            sign = 1
        elif cf < 0:
            sign = -1
        else:
            continue  # ignora zeros
        if last_sign != 0 and sign != last_sign:
            changes += 1
        last_sign = sign
    return changes


def _newton_raphson_irr(
    full_cashflows: List[float],
    guess: float,
    max_iterations: int,
    tolerance: float,
) -> Optional[float]:
    """
    Executa uma tentativa de Newton-Raphson para encontrar a TIR.

    Args:
        full_cashflows: Fluxo completo incluindo -I no período 0.
        guess: Chute inicial da taxa.
        max_iterations: Máximo de iterações.
        tolerance: Critério de parada.

    Returns:
        Taxa convergida ou None.
    """
    rate = guess

    for _ in range(max_iterations):
        npv = 0.0
        dnpv = 0.0

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
                return None
            return rate_new

        rate = rate_new

    return None


__all__ = [
    "IRRResult",
    "calculate_npv",
    "calculate_irr",
    "discount_cashflow",
    "present_value_annuity",
    "future_value_annuity",
]
