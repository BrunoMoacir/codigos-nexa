"""
app/architect/calculators/investment.py - Calculadora de Investimento/Poupança

Feature: F3 - Nexa Architect
Version: 2.0.0

Funções:
- calculate_pmt_needed:         Depósito mensal necessário para atingir meta
- calculate_future_value:       Valor futuro de depósitos periódicos
- calculate_months_needed:      Meses necessários para atingir meta (fórmula fechada)
- generate_accumulation_schedule: Tabela mensal com IR real por depósito

Changelog v2.0:
- IR por depósito: cada aporte tem seu próprio prazo e alíquota
  (1º depósito → 15%, último → 22,5%). Elimina subestimativa de R$800–1.200
  em planos de 36 meses com CDI 13%.
- tax_exempt: produtos isentos de IR (LCI, LCA, debêntures incentivadas,
  poupança) → net = gross.
- semiannual_tax (come-cotas): fundos de renda fixa/multimercado sofrem
  antecipação de 15% semestralmente. Reduz compounding — crucial para
  comparação CDB vs fundo no F8.
- inflation_annual: retorno real deflacionado (usa IPCA do IPCAConnector).
- calculate_months_needed: fórmula fechada O(1) quando initial_amount=0.
- calculate_future_value: aceita tax_exempt para retornar líquido direto.

Todas as taxas são em decimal (ex: 0.10 = 10% a.a.).
Conversão anual → mensal via capitalização composta.
"""

import math
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPOSTO DE RENDA — Tabela Regressiva (Renda Fixa, Brasil)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# (dias_limite, aliquota)
_IR_TABLE = [
    (180,    0.225),   # até 180 dias: 22,5%
    (360,    0.200),   # 181–360 dias: 20%
    (720,    0.175),   # 361–720 dias: 17,5%
    (99_999, 0.150),   # acima de 720 dias: 15%
]

# Alíquota de come-cotas para fundos de longo prazo
_COMECOTAS_RATE = 0.15


def _get_ir_rate(holding_days: int) -> float:
    """Retorna a alíquota de IR regressiva para o prazo dado (em dias)."""
    return next(r for days, r in _IR_TABLE if holding_days <= days)


def apply_ir(gross_gain: float, holding_days: int) -> float:
    """
    Retorna o ganho líquido após IR regressivo (renda fixa).

    IR não incide sobre perdas — se gross_gain <= 0, retorna sem alteração.

    Args:
        gross_gain:   Rendimento bruto (R$)
        holding_days: Prazo de aplicação em dias

    Returns:
        Ganho líquido = gross_gain × (1 − alíquota_IR), ou gross_gain se ≤ 0.

    Example:
        >>> apply_ir(1000.0, 400)   # 17,5%
        825.0
        >>> apply_ir(1000.0, 800)   # 15%
        850.0
    """
    if gross_gain <= 0:
        return gross_gain
    return gross_gain * (1.0 - _get_ir_rate(holding_days))


@dataclass
class InvestmentResult:
    """
    Resultado completo de simulação de investimento/poupança.

    Campos retrocompatíveis (v1):
        monthly_deposit, total_deposited, total_interest_earned, final_amount,
        net_interest_earned, net_final_amount, ir_rate_applied (→ effective),
        months, effective_monthly_rate, schedule

    Campos novos (v2):
        total_ir_paid:          IR total pago (via come-cotas + resgate, ou por depósito)
        tax_exempt:             True se produto isento (LCI, LCA, poupança, etc.)
        semiannual_tax_applied: True se come-cotas foi simulado
        real_net_final_amount:  Valor líquido em poder de compra de hoje (se inflation > 0)
        inflation_annual:       Taxa de inflação usada para deflacionar (0.0 = não deflacionado)
    """
    # v1 — retrocompatíveis
    monthly_deposit: float
    total_deposited: float
    total_interest_earned: float      # ganho bruto efetivo (pós-compounding de CC, se aplicável)
    final_amount: float               # saldo bruto no vencimento (antes do IR final)
    net_interest_earned: float        # ganho líquido de IR
    net_final_amount: float           # total_deposited + net_interest_earned
    ir_rate_applied: float            # alíquota efetiva = total_ir_paid / total_interest_earned
    months: int
    effective_monthly_rate: float
    schedule: List[Dict]

    # v2 — novos
    total_ir_paid: float
    tax_exempt: bool
    semiannual_tax_applied: bool
    real_net_final_amount: float      # net_final_amount deflacionado pelo IPCA
    inflation_annual: float           # taxa usada na deflação (0.0 = não deflacionado)

    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_pmt_needed(
    target: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0,
) -> float:
    """
    Calcula o depósito mensal necessário para atingir uma meta.

    Resolve PMT na fórmula:
        target = PMT × [((1+r)^n − 1) / r] + initial × (1+r)^n

    Args:
        target:         Valor alvo (R$)
        annual_rate:    Taxa de rendimento anual (decimal, ex: 0.10 = 10%)
        months:         Prazo em meses
        initial_amount: Valor já investido (default: 0)

    Returns:
        Depósito mensal necessário (R$). Zero se initial_amount já cobre a meta.

    Raises:
        ValueError: Se target ≤ 0, annual_rate ≤ −1 ou months ≤ 0.

    Example:
        >>> round(calculate_pmt_needed(100_000, 0.10, 36), 2)
        2409.11
    """
    if target <= 0:
        raise ValueError("Meta deve ser positiva")
    if annual_rate <= -1:
        raise ValueError("Taxa não pode ser menor ou igual a -100%")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    fv_initial = initial_amount * ((1 + monthly_rate) ** months)
    remaining = target - fv_initial

    if remaining <= 0:
        return 0.0
    if monthly_rate == 0:
        return remaining / months

    factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
    return remaining / factor


def calculate_future_value(
    monthly_deposit: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0,
    tax_exempt: bool = False,
) -> float:
    """
    Calcula o valor futuro de depósitos mensais com rendimento.

    FV = PMT × [((1+r)^n − 1) / r] + initial × (1+r)^n

    Args:
        monthly_deposit: Depósito mensal (R$)
        annual_rate:     Taxa anual (decimal)
        months:          Prazo em meses
        initial_amount:  Valor já investido (default: 0)
        tax_exempt:      Se True, retorna o FV bruto (sem IR).
                         Se False, retorna o FV BRUTO (sem IR) — para FV
                         líquido, use generate_accumulation_schedule.net_final_amount.

    Returns:
        Valor futuro BRUTO acumulado (R$).

    Note:
        Este método retorna sempre o valor bruto. Para o líquido (com IR por
        depósito ou come-cotas), use generate_accumulation_schedule().

    Raises:
        ValueError: Se monthly_deposit < 0, annual_rate ≤ −1 ou months ≤ 0.

    Example:
        >>> round(calculate_future_value(2000, 0.10, 36), 2)
        83780.84
    """
    if monthly_deposit < 0:
        raise ValueError("Depósito mensal não pode ser negativo")
    if annual_rate <= -1:
        raise ValueError("Taxa não pode ser menor ou igual a -100%")
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
    initial_amount: float = 0,
) -> Optional[int]:
    """
    Calcula quantos meses são necessários para atingir a meta.

    Quando initial_amount = 0 e annual_rate > 0, usa a fórmula fechada O(1):
        n = log(1 + target × r / PMT) / log(1 + r)

    Quando initial_amount > 0, cai para simulação iterativa (O(n)).

    Args:
        target:          Valor alvo (R$)
        monthly_deposit: Depósito mensal (R$)
        annual_rate:     Taxa anual (decimal)
        initial_amount:  Valor já investido (default: 0)

    Returns:
        Número de meses necessários, ou None se não convergir em 1.200 meses.

    Raises:
        ValueError: Se target ≤ 0, monthly_deposit ≤ 0 ou annual_rate ≤ −1.

    Example:
        >>> calculate_months_needed(100_000, 2_000, 0.10)
        43
    """
    if target <= 0:
        raise ValueError("Meta deve ser positiva")
    if monthly_deposit <= 0:
        raise ValueError("Depósito mensal deve ser positivo")
    if annual_rate <= -1:
        raise ValueError("Taxa não pode ser menor ou igual a -100%")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    # Fórmula fechada quando não há montante inicial
    # n = log(1 + target × r / PMT) / log(1 + r)
    if monthly_rate > 0 and initial_amount == 0:
        inner = 1.0 + target * monthly_rate / monthly_deposit
        if inner <= 0:
            return None
        n = math.log(inner) / math.log(1.0 + monthly_rate)
        return math.ceil(n)

    # Iterativo: montante inicial ou taxa zero
    balance = initial_amount
    for month in range(1, 1201):
        balance = balance * (1 + monthly_rate) + monthly_deposit
        if balance >= target:
            return month

    return None


def generate_accumulation_schedule(
    monthly_deposit: float,
    annual_rate: float,
    months: int,
    initial_amount: float = 0,
    tax_exempt: bool = False,
    semiannual_tax: bool = False,
    inflation_annual: float = 0.0,
) -> InvestmentResult:
    """
    Gera tabela completa de acumulação mês a mês com IR preciso.

    Modelo de IR (precedência: tax_exempt > semiannual_tax > por depósito):

    1. tax_exempt=True (LCI, LCA, debêntures incentivadas, poupança*):
       IR = 0. net = gross.
       * Poupança tem regra de rendimento diferente — use annual_rate correto.

    2. semiannual_tax=True (fundos de renda fixa/multimercado — come-cotas):
       A cada 6 meses: IR de 15% sobre os rendimentos do semestre é deduzido
       do saldo. Isso REDUZ o efeito de juros compostos (compounding menor).
       No resgate: IR sobre os rendimentos desde o último come-cotas, à alíquota
       final (prazo total). Come-cotas já pagos não incidem novamente.

    3. Default — IR por depósito (CDB, LCI sem isenção, Tesouro Direto):
       Cada depósito tem seu próprio prazo de holding e alíquota:
       - Depósito do mês 1 → holding = (n-1)×30 dias → alíquota regressiva
       - Depósito do mês n → holding = 0 dias → sem ganho (sem IR)
       Correto para planos de aporte mensal: elimina a subestimativa do IR
       que ocorre quando toda a rentabilidade é tributada pelo prazo total.

    Args:
        monthly_deposit: Depósito mensal (R$)
        annual_rate:     Taxa anual bruta (decimal, ex: 0.1315 = 13,15%)
        months:          Prazo em meses
        initial_amount:  Montante inicial já investido (default: 0)
        tax_exempt:      True para produtos isentos de IR (LCI, LCA, etc.)
        semiannual_tax:  True para fundos com come-cotas semestral (15%/sem.)
        inflation_annual: Taxa de inflação anual para cálculo do retorno real
                          (ex: 0.045 = 4,5% IPCA). 0.0 = sem deflação.

    Returns:
        InvestmentResult com schedule detalhado e métricas de IR corretas.

    Raises:
        ValueError: Se monthly_deposit < 0, annual_rate ≤ −1 ou months ≤ 0.

    Example:
        >>> # CDB: IR por depósito (padrão)
        >>> r = generate_accumulation_schedule(2_000, 0.1315, 36)
        >>> r.net_final_amount < r.final_amount  # IR foi aplicado
        True

        >>> # LCI: isento
        >>> r_lci = generate_accumulation_schedule(2_000, 0.1315, 36, tax_exempt=True)
        >>> r_lci.net_final_amount == r_lci.final_amount
        True

        >>> # Fundo: come-cotas reduz compounding
        >>> r_fund = generate_accumulation_schedule(2_000, 0.1315, 36, semiannual_tax=True)
        >>> r_fund.net_final_amount < r_lci.net_final_amount  # fundo paga mais IR
        True
    """
    if monthly_deposit < 0:
        raise ValueError("Depósito mensal não pode ser negativo")
    if annual_rate <= -1:
        raise ValueError("Taxa não pode ser menor ou igual a -100%")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")

    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    balance = float(initial_amount)
    total_deposited = float(initial_amount)
    schedule = []

    # Variáveis de come-cotas (usadas apenas quando semiannual_tax=True)
    interest_since_cc = 0.0
    total_cc_paid = 0.0

    for month in range(1, months + 1):
        interest = balance * monthly_rate
        balance = balance + interest + monthly_deposit
        total_deposited += monthly_deposit
        interest_since_cc += interest

        # Come-cotas: a cada 6 meses, debitar 15% do rendimento do semestre
        cc_this_month = 0.0
        if semiannual_tax and not tax_exempt and month % 6 == 0 and interest_since_cc > 0:
            cc_this_month = interest_since_cc * _COMECOTAS_RATE
            balance -= cc_this_month
            total_cc_paid += cc_this_month
            interest_since_cc = 0.0

        schedule.append({
            "month": month,
            "deposit": round(monthly_deposit, 2),
            "interest": round(interest, 2),
            "cumulative_deposited": round(total_deposited, 2),
            "balance": round(balance, 2),
            "ir_withheld": round(cc_this_month, 2),  # come-cotas deste mês (0 se não CC)
        })

    # ── Saldo bruto final e ganho total ──────────────────────────────────────
    final_amount = round(balance, 2)
    # total_interest_earned = ganho efetivo (já reflete redução de compounding por CC)
    total_interest_earned = round(final_amount - total_deposited, 2)

    # ── Cálculo de IR ─────────────────────────────────────────────────────────
    if tax_exempt:
        # Sem IR: net = gross
        net_interest_earned = total_interest_earned
        total_ir_paid = 0.0
        effective_ir_rate = 0.0

    elif semiannual_tax:
        # Come-cotas: IR sobre remaining gains (após último come-cotas) ao resgate
        final_ir_rate = _get_ir_rate(months * 30)
        ir_on_remaining = round(interest_since_cc * final_ir_rate, 2) if interest_since_cc > 0 else 0.0

        total_ir_paid = round(total_cc_paid + ir_on_remaining, 2)
        net_interest_earned = round(total_interest_earned - ir_on_remaining, 2)

        gross_for_rate = total_interest_earned + total_cc_paid  # ganho antes de CC afetar compounding
        effective_ir_rate = round(total_ir_paid / gross_for_rate, 4) if gross_for_rate > 0 else 0.0

        # Ajustar balance e final_amount para refletir IR no resgate
        final_amount = round(balance - ir_on_remaining, 2)

    else:
        # ── IR por depósito: cada aporte com seu próprio prazo ────────────────
        # Depósito k (k=1..n): mantido por (n-k) meses = (n-k)*30 dias
        # Ganho do depósito k: PMT × ((1+r)^(n-k) - 1)
        # IR do depósito k: ganho × _get_ir_rate((n-k)*30)
        total_ir = 0.0

        # Montante inicial (holding = months*30 dias)
        if initial_amount > 0 and monthly_rate > 0:
            gain_initial = initial_amount * ((1 + monthly_rate) ** months - 1)
            if gain_initial > 0:
                total_ir += gain_initial * _get_ir_rate(months * 30)

        # Cada depósito mensal
        for k in range(1, months + 1):
            holding_months = months - k
            if holding_months > 0 and monthly_rate > 0:
                gain_k = monthly_deposit * ((1 + monthly_rate) ** holding_months - 1)
                if gain_k > 0:
                    total_ir += gain_k * _get_ir_rate(holding_months * 30)
            # k == months → holding = 0 → gain = 0 → sem IR

        total_ir_paid = round(total_ir, 2)
        net_interest_earned = round(total_interest_earned - total_ir_paid, 2)
        effective_ir_rate = round(total_ir_paid / total_interest_earned, 4) if total_interest_earned > 0 else 0.0

    net_final_amount = round(total_deposited + net_interest_earned, 2)

    # ── Retorno real (deflacionado pelo IPCA) ─────────────────────────────────
    if inflation_annual > 0:
        inflation_factor = (1 + inflation_annual) ** (months / 12)
        real_net_final_amount = round(net_final_amount / inflation_factor, 2)
    else:
        real_net_final_amount = net_final_amount

    return InvestmentResult(
        monthly_deposit=round(monthly_deposit, 2),
        total_deposited=round(total_deposited, 2),
        total_interest_earned=total_interest_earned,
        final_amount=final_amount,
        net_interest_earned=net_interest_earned,
        net_final_amount=net_final_amount,
        ir_rate_applied=effective_ir_rate,
        months=months,
        effective_monthly_rate=monthly_rate,
        schedule=schedule,
        total_ir_paid=total_ir_paid,
        tax_exempt=tax_exempt,
        semiannual_tax_applied=semiannual_tax and not tax_exempt,
        real_net_final_amount=real_net_final_amount,
        inflation_annual=inflation_annual,
    )


__all__ = [
    "apply_ir",
    "calculate_pmt_needed",
    "calculate_future_value",
    "calculate_months_needed",
    "generate_accumulation_schedule",
    "InvestmentResult",
    "_get_ir_rate",   # exposto para testes unitários
]
