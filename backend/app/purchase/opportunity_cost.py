"""
app/purchase/opportunity_cost.py — Custo de Oportunidade de Capital

Calcula quanto o capital PODERIA render no CDI caso não fosse desembolsado
à vista. Usado pelo PurchaseAdvisor para ajustar o net_cost_real de cada
opção de pagamento.

Fórmulas:
  PIX/cartão à vista:
    opportunity_cost = amount × cdi_net_monthly
    net_cost_real    = amount - reward + opportunity_cost

  Cartão parcelado sem juros (n parcelas):
    ganho_k = (P/n) × ((1 + r_net)^(n-k) - 1)   para k = 1..n
    ganho_total = Σ ganho_k
    net_cost_real = P - reward - ganho_total

  Financiamento CDC (com juros):
    O banco já precificou o tempo — sem ganho de oportunidade.
    net_cost_real = total_cost - reward  (sem mudança)
"""

from __future__ import annotations

from app.purchase.models import PaymentMethod, PaymentOption

# Tabela regressiva de IR sobre rendimento de renda fixa
_IR_BY_MONTHS = [
    (6,  0.225),   # até 180 dias (≤ 6 meses)
    (12, 0.200),   # 181–360 dias (≤ 12 meses)
    (24, 0.175),   # 361–720 dias (≤ 24 meses)
    (99, 0.150),   # acima de 720 dias
]

# CDI anual de fallback se BacenConnector estiver indisponível
_CDI_FALLBACK = 0.1475  # 14,75% a.a. (SELIC referência abr/2026)


def _ir_rate(installments: int) -> float:
    """Retorna alíquota de IR pela tabela regressiva com base no prazo em meses."""
    for months_limit, rate in _IR_BY_MONTHS:
        if installments <= months_limit:
            return rate
    return 0.15


def _cdi_net_monthly(cdi_annual: float, installments: int) -> float:
    """CDI mensal líquido de IR: (1 + cdi_annual)^(1/12) - 1, após IR."""
    ir = _ir_rate(installments)
    cdi_monthly_gross = (1 + cdi_annual) ** (1 / 12) - 1
    return cdi_monthly_gross * (1 - ir)


def apply_opportunity_cost(
    option: PaymentOption,
    cdi_annual: float = _CDI_FALLBACK,
) -> PaymentOption:
    """
    Recalcula ``net_cost_real`` de uma PaymentOption considerando o ganho
    ou custo de oportunidade de capital ao CDI.

    Retorna uma nova instância com os campos atualizados:
      - ``opportunity_cost_gain``: magnitude do ajuste CDI em R$
      - ``net_cost_real``:
          PIX/à vista   → net_cost + gain  (capital imobilizado = custo)
          Parcelado s/j → net_cost - gain  (capital investido mês a mês = benefício)
          Financiamento → net_cost         (sem ajuste — juros já precificam o tempo)

    Não modifica opções de FINANCIAMENTO (juros já estão no total_cost).
    """
    amount = option.total_cost
    reward = option.reward_value
    n = option.installments or 1

    if option.method == PaymentMethod.FINANCIAMENTO:
        # Juros CDC já precificam o custo do tempo — sem ajuste CDI
        gain = 0.0
        net_cost_real = round(amount - reward, 2)
    elif option.method in (PaymentMethod.PIX_AVISTA, PaymentMethod.CARTAO_AVISTA):
        # Desembolso integral hoje → capital imobilizado (CUSTO de oportunidade)
        # O capital NÃO pode ser investido → penalidade somada ao net_cost
        r = _cdi_net_monthly(cdi_annual, installments=1)
        gain = round(amount * r, 2)
        net_cost_real = round(amount - reward + gain, 2)  # + porque é custo, não ganho
    else:
        # Cartão parcelado sem juros: capital liberado mês a mês rende CDI (GANHO)
        # O capital permanece investido enquanto as parcelas vencem → benefício subtraído
        r = _cdi_net_monthly(cdi_annual, installments=n)
        gain = round(
            sum((amount / n) * ((1 + r) ** (n - k) - 1) for k in range(1, n + 1)),
            2,
        )
        net_cost_real = round(amount - reward - gain, 2)  # - porque é ganho real

    return option.model_copy(update={
        "opportunity_cost_gain": gain,
        "net_cost_real": net_cost_real,
    })
