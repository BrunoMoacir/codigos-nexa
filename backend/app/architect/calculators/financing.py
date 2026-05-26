"""
app/architect/calculators/financing.py - Calculadora de Financiamento

Feature: F3 - Nexa Architect
Version: 2.0.0

Sistemas de Amortização:
- PRICE: Parcelas fixas (Sistema Francês)
- SAC:   Amortização constante, com suporte a correção monetária (TR/IPCA)

Custos incluídos:
- Juros mensais
- IOF real (0,38% fixo + 0,0082%/dia sobre saldo, cap 3%) — Res. BACEN 3.516/2007
- Seguro mensal sobre saldo devedor (MIP/DFI imóvel, seguro auto veículo)
- Tarifas administrativas
- Correção monetária mensal do saldo (SAC — TR ou IPCA)

Changelog v2.0.0:
- IOF corrigido: duas componentes (fixo + diário), cap 3% do principal
- Seguro obrigatório parametrizável por tipo de bem
- Correção monetária (TR/IPCA) no SAC — saldo devedor reajustado mensalmente
- total_insurance adicionado ao FinancingResult e ao schedule
- monetary_correction adicionado ao schedule do SAC
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IOF — Resolução BACEN 3.516/2007 e alterações
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IOF_FIXO_RATE = 0.0038          # 0,38% sobre o principal (componente fixa)
IOF_DIARIO_RATE = 0.000082      # 0,0082% por dia sobre o saldo de cada parcela
IOF_DAILY_CAP_DAYS = 365        # máximo de dias considerados para o IOF diário
IOF_MAX_RATE = 0.030            # cap de 3% do principal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Seguros obrigatórios — taxas mensais sobre saldo devedor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Imóvel: MIP (Morte/Invalidez) + DFI (Danos Físicos) — faixa SUSEP/Caixa
# Veículo: seguro auto compulsório — faixa média do mercado
# Valores representativos; produção deve usar tabelas do segurador contratado.

INSURANCE_RATES = {
    "property":   0.00035,   # ~0,035%/mês sobre saldo (MIP+DFI combinados)
    "vehicle":    0.00200,   # ~0,20%/mês sobre saldo (seguro auto estimado)
    "motorcycle": 0.00180,
    "truck":      0.00150,
    "other":      0.0,       # sem seguro padrão para outros tipos
}


@dataclass
class FinancingResult:
    """
    Resultado completo de simulação de financiamento.

    Campos retrocompatíveis (v1):
        monthly_payment, total_paid, total_interest, total_iof,
        admin_fee, total_cost, schedule, cet_annual

    Campos novos (v2):
        total_insurance:         Total de seguro pago ao longo do contrato
        iof_fixed_component:     Componente fixa do IOF (0,38%)
        iof_daily_component:     Componente diária acumulada (0,0082%/dia)
        monetary_correction_annual: Taxa de correção monetária aplicada (0 = sem)
    """
    # v1 — retrocompatíveis
    monthly_payment: float
    total_paid: float
    total_interest: float
    total_iof: float
    admin_fee: float
    total_cost: float
    schedule: List[Dict]
    cet_annual: float

    # v2 — novos
    total_insurance: float
    iof_fixed_component: float
    iof_daily_component: float
    monetary_correction_annual: float

    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_price(
    principal: float,
    annual_rate: float,
    months: int,
    iof_rate: float = IOF_FIXO_RATE,   # mantido para compat; usado como base fixa
    admin_fee: float = 0.0,
    insurance_monthly_rate: Optional[float] = None,
    asset_type: str = "other",
) -> FinancingResult:
    """
    Calcula financiamento pelo sistema PRICE (parcelas fixas).

    No sistema PRICE, a parcela é constante durante todo o prazo.
    Inicialmente, a maior parte é juros; ao final, é amortização.

    Args:
        principal:               Valor financiado (R$)
        annual_rate:             Taxa de juros anual (decimal, ex: 0.12 = 12%)
        months:                  Prazo em meses
        iof_rate:                Taxa base fixa do IOF (default: 0,38%).
                                 O IOF diário (0,0082%/dia) é sempre somado.
        admin_fee:               Tarifa administrativa única (R$)
        insurance_monthly_rate:  Seguro mensal sobre saldo devedor (decimal).
                                 Se None, usa a taxa padrão do asset_type.
        asset_type:              Tipo de bem — define seguro padrão quando
                                 insurance_monthly_rate é None.
                                 Valores: 'property', 'vehicle', 'motorcycle',
                                 'truck', 'other'

    Returns:
        FinancingResult com todos os detalhes

    Fórmula PRICE:
        PMT = P × [r(1+r)^n / ((1+r)^n - 1)]
    """
    _validate(principal, annual_rate, months)

    ins_rate = _resolve_insurance_rate(insurance_monthly_rate, asset_type)
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    # Parcela PRICE
    if monthly_rate == 0:
        pmt = principal / months
    else:
        factor = (1 + monthly_rate) ** months
        pmt = principal * (monthly_rate * factor) / (factor - 1)

    # Tabela de amortização
    schedule = []
    balance = principal

    for month in range(1, months + 1):
        interest = balance * monthly_rate
        amortization = pmt - interest
        insurance = balance * ins_rate
        balance -= amortization
        if month == months:
            balance = 0.0

        schedule.append({
            "month": month,
            "payment": round(pmt, 2),
            "interest": round(interest, 2),
            "amortization": round(amortization, 2),
            "insurance": round(insurance, 2),
            "balance": round(max(0.0, balance), 2),
        })

    # IOF real (duas componentes)
    iof_fixed, iof_daily, total_iof = _calculate_iof(principal, schedule, iof_rate)

    # Totais
    total_interest = sum(r["interest"] for r in schedule)
    total_paid_base = sum(r["payment"] for r in schedule)
    total_insurance = sum(r["insurance"] for r in schedule)
    total_cost = total_paid_base + total_insurance + total_iof + admin_fee

    # CET: o principal líquido é o valor recebido pelo tomador
    principal_liquido = principal - total_iof - admin_fee
    payments_cet = [r["payment"] + r["insurance"] for r in schedule]
    cet_annual = _calculate_cet(principal_liquido, payments_cet)

    return FinancingResult(
        monthly_payment=round(pmt, 2),
        total_paid=round(total_paid_base, 2),
        total_interest=round(total_interest, 2),
        total_iof=round(total_iof, 2),
        admin_fee=round(admin_fee, 2),
        total_cost=round(total_cost, 2),
        schedule=schedule,
        cet_annual=cet_annual,
        total_insurance=round(total_insurance, 2),
        iof_fixed_component=round(iof_fixed, 2),
        iof_daily_component=round(iof_daily, 2),
        monetary_correction_annual=0.0,
    )


def calculate_sac(
    principal: float,
    annual_rate: float,
    months: int,
    iof_rate: float = IOF_FIXO_RATE,
    admin_fee: float = 0.0,
    insurance_monthly_rate: Optional[float] = None,
    asset_type: str = "other",
    monetary_correction_annual: float = 0.0,
) -> FinancingResult:
    """
    Calcula financiamento pelo sistema SAC (amortização constante).

    No SAC, a amortização é constante. As parcelas são decrescentes pois
    os juros diminuem conforme o saldo devedor cai.

    Quando monetary_correction_annual > 0 (ex: TR ≈ 0.02, IPCA ≈ 0.045),
    o saldo devedor é reajustado mensalmente antes do cálculo dos juros.
    Isso modela o SAC+TR típico do SFH (Caixa, SBPE).

    Args:
        principal:                   Valor financiado (R$)
        annual_rate:                 Taxa de juros anual (decimal)
        months:                      Prazo em meses
        iof_rate:                    Taxa base fixa do IOF (default: 0,38%)
        admin_fee:                   Tarifa administrativa única (R$)
        insurance_monthly_rate:      Seguro mensal sobre saldo (decimal).
                                     Se None, usa padrão do asset_type.
        asset_type:                  Tipo de bem para seguro padrão.
        monetary_correction_annual:  Índice anual de correção monetária
                                     (decimal). Ex: 0.02 para TR de 2%,
                                     0.045 para IPCA de 4,5%.
                                     0.0 = sem correção (comportamento v1).

    Returns:
        FinancingResult

    Fórmula SAC:
        Amortização = P / n (constante)
        Juros_t     = Saldo_corrigido_t × r
        Parcela_t   = Amortização + Juros_t + Correção_t  (decrescente)
    """
    _validate(principal, annual_rate, months)

    ins_rate = _resolve_insurance_rate(insurance_monthly_rate, asset_type)
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    monthly_corr = (1 + monetary_correction_annual) ** (1 / 12) - 1
    amortization = principal / months

    schedule = []
    balance = principal

    for month in range(1, months + 1):
        # 1. Reajuste do saldo pela correção monetária (TR/IPCA)
        correction = balance * monthly_corr
        balance_corrected = balance + correction

        # 2. Juros sobre saldo corrigido
        interest = balance_corrected * monthly_rate

        # 3. Seguro sobre saldo corrigido
        insurance = balance_corrected * ins_rate

        # 4. Parcela = amortização fixa + juros + correção
        payment = amortization + interest + correction

        # 5. Novo saldo (remove amortização do saldo corrigido)
        balance = balance_corrected - amortization
        if month == months:
            balance = 0.0

        schedule.append({
            "month": month,
            "payment": round(payment, 2),
            "interest": round(interest, 2),
            "amortization": round(amortization, 2),
            "monetary_correction": round(correction, 2),
            "insurance": round(insurance, 2),
            "balance": round(max(0.0, balance), 2),
        })

    # IOF real (duas componentes)
    iof_fixed, iof_daily, total_iof = _calculate_iof(principal, schedule, iof_rate)

    # Totais
    total_interest = sum(r["interest"] for r in schedule)
    total_paid_base = sum(r["payment"] for r in schedule)
    total_insurance = sum(r["insurance"] for r in schedule)
    total_cost = total_paid_base + total_insurance + total_iof + admin_fee

    principal_liquido = principal - total_iof - admin_fee
    payments_cet = [r["payment"] + r["insurance"] for r in schedule]
    cet_annual = _calculate_cet(principal_liquido, payments_cet)

    return FinancingResult(
        monthly_payment=round(schedule[0]["payment"], 2),
        total_paid=round(total_paid_base, 2),
        total_interest=round(total_interest, 2),
        total_iof=round(total_iof, 2),
        admin_fee=round(admin_fee, 2),
        total_cost=round(total_cost, 2),
        schedule=schedule,
        cet_annual=cet_annual,
        total_insurance=round(total_insurance, 2),
        iof_fixed_component=round(iof_fixed, 2),
        iof_daily_component=round(iof_daily, 2),
        monetary_correction_annual=monetary_correction_annual,
    )


def _calculate_iof(
    principal: float,
    schedule: List[Dict],
    iof_fixed_rate: float = IOF_FIXO_RATE,
) -> tuple[float, float, float]:
    """
    Calcula IOF real com duas componentes — Res. BACEN 3.516/2007.

    Componente 1 — IOF fixo (adicional):
        iof_fixo = iof_fixed_rate × principal

    Componente 2 — IOF diário (proporcional):
        Para cada mês t, a amortização representa o capital que ficou
        retido por (t × 30) dias (aproximação de 30 dias/mês).
        iof_diario = Σ [ amortizacao_t × 0,000082 × min(t×30, 365) ]

    Total = iof_fixo + iof_diario, limitado a 3% do principal.

    Args:
        principal:       Valor financiado
        schedule:        Tabela de amortização gerada
        iof_fixed_rate:  Taxa da componente fixa (default: 0,0038)

    Returns:
        Tuple (iof_fixo, iof_diario, iof_total)
    """
    # iof_fixed_rate == 0.0 sinaliza operação isenta (ex: SFH imobiliário).
    # Nesse caso, ambas as componentes são zero — não apenas a fixa.
    if iof_fixed_rate == 0.0:
        return 0.0, 0.0, 0.0

    iof_fixed = principal * iof_fixed_rate

    iof_daily = 0.0
    for row in schedule:
        month = row["month"]
        amort = row["amortization"]
        days = min(month * 30, IOF_DAILY_CAP_DAYS)
        iof_daily += amort * IOF_DIARIO_RATE * days

    total_iof = iof_fixed + iof_daily
    cap = principal * IOF_MAX_RATE
    total_iof = min(total_iof, cap)

    return iof_fixed, iof_daily, total_iof


def _resolve_insurance_rate(
    insurance_monthly_rate: Optional[float],
    asset_type: str,
) -> float:
    """Retorna a taxa de seguro mensal, respeitando override explícito."""
    if insurance_monthly_rate is not None:
        return insurance_monthly_rate
    return INSURANCE_RATES.get(asset_type, 0.0)


def _validate(principal: float, annual_rate: float, months: int) -> None:
    if principal <= 0:
        raise ValueError("Principal deve ser positivo")
    if annual_rate < 0:
        raise ValueError("Taxa não pode ser negativa")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")


def _calculate_cet(
    principal_liquido: float,
    payments: List[float],
    max_iterations: int = 100,
) -> float:
    """
    Calcula CET (Custo Efetivo Total) anualizado via Newton-Raphson.

    CET é a taxa mensal r que satisfaz:
        principal_liquido = Σ( payment_t / (1+r)^t )

    Funciona tanto para PRICE (parcelas iguais) quanto SAC (parcelas variáveis).

    Args:
        principal_liquido: Principal - IOF - tarifas
        payments:          Lista de parcelas mensais (já incluindo seguro)
        max_iterations:    Máximo de iterações Newton-Raphson

    Returns:
        CET anualizado (decimal). Retorna 0.0 se não convergir.
    """
    if principal_liquido <= 0:
        raise ValueError("Tarifas e IOF não podem exceder o principal")

    rate = 0.01  # chute inicial: 1% a.m.

    for _ in range(max_iterations):
        npv = 0.0
        dnpv = 0.0
        for t, pmt in enumerate(payments, start=1):
            denom = (1 + rate) ** t
            npv += pmt / denom
            dnpv -= t * pmt / ((1 + rate) ** (t + 1))

        if abs(dnpv) < 1e-10:
            break

        rate_new = rate - (npv - principal_liquido) / dnpv

        if abs(rate_new - rate) < 1e-6:
            if rate_new <= 0:
                return 0.0
            return (1 + rate_new) ** 12 - 1

        rate = rate_new

    if rate <= 0:
        return 0.0
    return (1 + rate) ** 12 - 1


def compare_methods(
    principal: float,
    annual_rate: float,
    months: int,
    asset_type: str = "other",
    monetary_correction_annual: float = 0.0,
) -> Dict[str, FinancingResult]:
    """
    Compara PRICE vs SAC lado a lado.

    Args:
        principal:                  Valor financiado
        annual_rate:                Taxa anual
        months:                     Prazo
        asset_type:                 Tipo de bem (para seguro padrão)
        monetary_correction_annual: Correção monetária anual (para SAC)

    Returns:
        Dict com resultados de ambos os métodos

    Example:
        >>> comparison = compare_methods(50000, 0.12, 48)
        >>> comparison["SAC"].total_cost < comparison["PRICE"].total_cost
        True
    """
    price = calculate_price(principal, annual_rate, months, asset_type=asset_type)
    sac = calculate_sac(
        principal, annual_rate, months,
        asset_type=asset_type,
        monetary_correction_annual=monetary_correction_annual,
    )
    return {"PRICE": price, "SAC": sac}


__all__ = [
    "calculate_price",
    "calculate_sac",
    "compare_methods",
    "FinancingResult",
    "INSURANCE_RATES",
    "IOF_FIXO_RATE",
    "IOF_DIARIO_RATE",
    "IOF_MAX_RATE",
]
