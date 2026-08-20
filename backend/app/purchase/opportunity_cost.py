"""
app/purchase/opportunity_cost.py — Custo de Oportunidade de Capital

Traz as quatro opções de pagamento para o MESMO instante de referência (hoje),
descontando cada fluxo pelo CDI líquido de IR. Sem isso não há comparação: um
real pago hoje não é um real pago daqui a doze meses.

    net_cost_real = VPL(fluxo de pagamentos) − reward
    opportunity_cost_gain = nominal − VPL   (quanto vale adiar o desembolso)

Por opção:

  PIX à vista        paga hoje                 → VPL = preço, ganho = 0
  Cartão à vista     paga na fatura (~1 mês)   → VPL = preço/(1+r)
  Cartão parcelado   n parcelas, meses 1..n    → VPL = Σ (P/n)/(1+r)^k
  CDC                n prestações, meses 1..n  → VPL = Σ PMT/(1+r)^k

O que esta versão corrigiu, e por quê:

  • O cartão à vista recebia a MESMA penalidade do PIX (`+ P·r`), como se
    ambos saíssem do bolso hoje. Compra no cartão é paga na fatura, ~30 dias
    depois — é ganho, não penalidade. Com cashback zero as duas opções
    empatavam em centavos, quando o cartão é estritamente melhor.

  • O ganho do parcelado usava expoente `(n−k)`, que dá à PRIMEIRA parcela o
    maior rendimento e à última nenhum: é a convenção de pagamento no ato.
    Parcela de cartão cai na fatura seguinte, então o expoente é `k`. O erro
    subestimava o benefício em cerca de um período (R$ 157 contra R$ 186 numa
    compra de R$ 3.000 em 12x).

  • O CDC era medido em reais NOMINAIS somados (`PMT × n`) enquanto as outras
    opções ganhavam crédito de tempo — R$ 222 de inconsistência nos mesmos
    R$ 3.000 em 12x. A direção estava certa (o CDC é pior mesmo), mas comparar
    nominal contra descontado não é comparação.

O ranking segue por `net_cost_real` crescente. A diferença é que agora os
quatro números respondem à mesma pergunta.
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

# Meses entre a compra no cartão e o pagamento da fatura. Depende de quando a
# compra cai em relação ao fechamento (de ~1 a ~40 dias); 1 mês é o valor médio
# e é premissa declarada, não medição. O InvoiceHorizon sabe o dia de
# fechamento quando há dado — quando souber, é daqui que ele entra.
_FLOAT_CARTAO_MESES = 1.0


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


def _vpl_parcelas(valor_total: float, n: int, r: float) -> float:
    """VPL de `n` parcelas iguais pagas nos meses 1..n."""
    if n <= 0:
        return valor_total
    parcela = valor_total / n
    return sum(parcela / (1 + r) ** k for k in range(1, n + 1))


def apply_opportunity_cost(
    option: PaymentOption,
    cdi_annual: float = _CDI_FALLBACK,
) -> PaymentOption:
    """
    Recalcula ``net_cost_real`` trazendo o fluxo da opção a valor presente.

    Campos atualizados:
      - ``opportunity_cost_gain``: nominal − VPL, ou seja, quanto vale adiar
        o desembolso. Zero para quem paga hoje.
      - ``net_cost_real``: VPL − reward.
    """
    nominal = option.total_cost
    reward = option.reward_value
    n = option.installments or 1

    if option.method == PaymentMethod.PIX_AVISTA:
        # Único desembolso realmente feito hoje — é a referência do zero.
        vpl = nominal

    elif option.method == PaymentMethod.CARTAO_AVISTA:
        # Pago na fatura: o dinheiro rende até lá.
        r = _cdi_net_monthly(cdi_annual, installments=1)
        vpl = nominal / (1 + r) ** _FLOAT_CARTAO_MESES

    elif option.method == PaymentMethod.CARTAO_PARCELADO:
        # Parcelas caem nas faturas seguintes: meses 1..n.
        r = _cdi_net_monthly(cdi_annual, installments=n)
        vpl = _vpl_parcelas(nominal, n, r)

    else:  # FINANCIAMENTO (CDC)
        # As prestações também são futuras. Os juros do CDC já estão no
        # `total_cost`; descontar não os apaga — só põe o CDC na mesma régua.
        r = _cdi_net_monthly(cdi_annual, installments=n)
        vpl = _vpl_parcelas(nominal, n, r)

    return option.model_copy(update={
        "opportunity_cost_gain": round(nominal - vpl, 2),
        "net_cost_real": round(vpl - reward, 2),
    })
