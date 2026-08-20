"""
app/architect/simulators/cost_basis.py — Base de custo única (F3)

Feature: F3 - Nexa Architect

Por que este módulo existe:
    O StrategyEngine produz o NÚMERO ("financiar custa X") e o SensitivityAnalyzer
    produz o GRÁFICO que explica esse número ("se o CET subir 1 p.p., X vira Y").
    Os dois montavam o fluxo de caixa por conta própria, e divergiram:

    financiamento
        • sensibilidade chamava calculate_price/sac sem `asset_type`, o que zera
          o seguro obrigatório (a tabela é indexada por "property"/"vehicle");
        • não passava `iof_rate` nem somava o IOF de entrada em t=0
          → R$ 2.376 num veículo de R$ 64 mil.

    consórcio
        • sensibilidade omitia asset_type, annual_adjustment_rate, group_size,
          contemplated_per_month, bid_mean_initial e bid_std. Como
          annual_adjustment_rate é o reajuste da carta, o gráfico rodava com o
          default de 4,5% enquanto o número usava o IPCA real
          → R$ 8.568 (4,6% do VPL) e contemplação 31 meses diferente;
        • rodava 1 simulação de Monte Carlo contra as 2000 do motor. Uma amostra
          só não é estimativa pontual, é ruído — e num gráfico que mede a
          DIFERENÇA entre pontos o ruído engole o sinal.

    Corrigir os dois lados separadamente não resolve: eles voltam a divergir na
    próxima mudança. Aqui existe UMA implementação, e os dois chamam.

O que é legítimo divergir:
    `num_simulations`. O motor roda a distribuição inteira; a sensibilidade
    avalia dezenas de pontos e precisa de determinismo barato. Por isso é
    parâmetro explícito, com seed fixa — e não uma diferença acidental.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.architect.calculators import consortium as cons_calc
from app.architect.calculators import financing as fin_calc
from app.architect.rate_defaults import rate, rate_int

logger = logging.getLogger(__name__)

# Monte Carlo do motor: distribuição completa.
SIMS_MOTOR = 2000
# Monte Carlo da sensibilidade: determinístico e barato (~10 ms/ponto), mas
# longe do ruído de amostra única.
SIMS_SENSIBILIDADE = 400
SEED_SENSIBILIDADE = 42


# ── Financiamento ────────────────────────────────────────────────────────────

def simular_financiamento(
    request: Any,
    principal: float,
    cet_annual: float,
    months: int,
):
    """
    calculate_price/sac com o asset_type e o iof_rate corretos para o bem.

    Sem `asset_type` o seguro obrigatório é zerado; sem `iof_rate` o IOF sai do
    default em vez da tabela por ativo (imóvel no SFH é isento, veículo não).
    """
    from app.architect.simulators.strategy_engine import (
        _CALC_ASSET_MAP,
        _IOF_RATE_BY_ASSET,
    )

    asset    = _CALC_ASSET_MAP.get(request.asset_type, "other")
    iof_rate = _IOF_RATE_BY_ASSET.get(request.asset_type, fin_calc.IOF_FIXO_RATE)

    calc = (fin_calc.calculate_sac
            if request.amortization_method.value == "SAC"
            else fin_calc.calculate_price)
    return calc(principal, cet_annual, months, iof_rate=iof_rate, asset_type=asset)


def fluxo_financiamento(down_payment: float, sim) -> List[float]:
    """Entrada + IOF em t=0; depois parcela + seguro, mês a mês."""
    return [-(down_payment + sim.total_iof)] + [
        -(row["payment"] + row.get("insurance", 0.0)) for row in sim.schedule
    ]


# ── Preço do bem ao longo da acumulação ──────────────────────────────────────

def taxa_reajuste_do_bem(asset_type, market_rates: Dict[str, float]) -> float:
    """
    Quanto o preço do bem sobe por ano enquanto o usuário poupa para comprá-lo.

    Imóvel usa a premissa de valorização do simulador macro; os demais bens usam
    o IPCA — o preço de um carro ou de uma reforma acompanha a inflação geral, e
    não existe índice específico no projeto para afirmar outra coisa. Assumir
    zero seria pior: é justamente o congelamento que este módulo corrige.
    """
    from app.architect.models import AssetType
    from app.architect.simulators.macro_scenario import _APPR_MU_ANNUAL

    if asset_type == AssetType.IMOVEL:
        return _APPR_MU_ANNUAL
    return rate(market_rates, "ipca_annual")


def preco_do_bem_em(
    request: Any, market_rates: Dict[str, float], months: int
) -> float:
    """Preço do bem daqui a `months` meses."""
    g = taxa_reajuste_do_bem(request.asset_type, market_rates)
    return float(request.target_amount) * (1.0 + g) ** (months / 12.0)


def _saldo_menos_preco(request, g_m: float, r_m: float, deposito: float, n: int) -> float:
    """
    Saldo acumulado menos o preço do bem no mês n.

    saldo(n) = entrada·(1+r)ⁿ + PMT·((1+r)ⁿ−1)/r
    preço(n) = alvo·(1+g)ⁿ
    """
    x = (1.0 + r_m) ** n
    saldo = float(request.down_payment) * x
    saldo += deposito * ((x - 1.0) / r_m if r_m > 0 else n)
    return saldo - float(request.target_amount) * (1.0 + g_m) ** n


def meses_para_alcancar_o_bem(
    request: Any,
    market_rates: Dict[str, float],
    monthly_deposit: float,
    investment_rate: float,
    limite: int = 600,
) -> Optional[int]:
    """
    Meses até o patrimônio acumulado alcançar o PREÇO DO BEM NAQUELE MÊS.

    A versão anterior mirava `target_amount` — o preço de hoje, congelado —
    enquanto o aluguel pago durante a espera era corrigido pelo IPCA mês a mês.
    O modelo encarecia a espera de um lado e a congelava do outro, e o viés
    tinha direção única: inflava SAVE_INVEST, a estratégia concorrente do
    financiamento. Num imóvel de R$ 300 mil com 120 meses de acumulação, o
    aporte pedido era R$ 616 contra os R$ 1.742 de que a pessoa precisaria.

    Devolve None quando o bem sobe mais rápido do que o dinheiro rende: aí a
    meta se afasta a cada mês e poupar não alcança. Não é falha de cálculo, é
    o resultado — e o usuário precisa vê-lo em vez de receber um prazo falso.

    Busca por BISSEÇÃO (~10 avaliações), não mês a mês: a versão iterativa de
    `calculate_months_needed` roda até 1200 passos em Python puro e, com o alvo
    móvel, deixou de convergir cedo — sozinha, multiplicou por 5 o tempo da
    suíte do architect.
    """
    g_m = (1.0 + taxa_reajuste_do_bem(request.asset_type, market_rates)) ** (1/12) - 1
    r_m = (1.0 + investment_rate) ** (1/12) - 1

    def f(n: int) -> float:
        return _saldo_menos_preco(request, g_m, r_m, monthly_deposit, n)

    if f(1) >= 0:
        return 1
    if f(limite) < 0:
        # Não alcança dentro do horizonte — tipicamente porque o bem sobe mais
        # rápido do que o dinheiro rende.
        return None

    lo, hi = 1, limite
    while lo < hi:
        meio = (lo + hi) // 2
        if f(meio) >= 0:
            hi = meio
        else:
            lo = meio + 1
    return lo


def aporte_para_alcancar_o_bem(
    request: Any,
    market_rates: Dict[str, float],
    investment_rate: float,
    months: int,
) -> float:
    """Aporte mensal necessário para comprar o bem PELO PREÇO QUE ELE TERÁ."""
    from app.architect.calculators import investment as inv_calc

    return inv_calc.calculate_pmt_needed(
        preco_do_bem_em(request, market_rates, months),
        investment_rate,
        months,
        request.down_payment,
    )


# ── Consórcio ────────────────────────────────────────────────────────────────

def simular_consorcio(
    request: Any,
    market_rates: Dict[str, float],
    bid_amount: float,
    *,
    num_simulations: int = SIMS_MOTOR,
    seed: int | None = None,
    sorteio_share: float | None = None,
):
    """
    Monte Carlo de consórcio com o conjunto COMPLETO de parâmetros do grupo.

    `num_simulations`/`seed` são explícitos porque são a única divergência
    legítima entre o motor e a curva de sensibilidade.

    `sorteio_share` fixo desliga a propagação de incerteza dos parâmetros do
    grupo. O motor a mantém ligada — o intervalo que o usuário lê precisa
    incluir o que não se sabe sobre o grupo. A curva de sensibilidade a
    desliga: ali o objetivo é isolar UMA variável, e ruído de parâmetro em cada
    ponto mede ruído, não sensibilidade.
    """
    from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider

    return cons_calc.calculate_consortium_metrics(
        letter_value=request.target_amount,
        months=rate_int(market_rates, "consortium_months"),
        admin_rate=rate(market_rates, "consortium_admin_rate"),
        reserve_fund_rate=rate(market_rates, "consortium_reserve_fund_rate"),
        bid_amount=bid_amount,
        asset_type=ConsortiumRateProvider.map_asset_type(request.asset_type.value),
        annual_adjustment_rate=rate(market_rates, "consortium_annual_adjustment_rate"),
        group_size=rate_int(market_rates, "consortium_group_size"),
        contemplated_per_month=rate_int(market_rates, "consortium_contemplated_per_month"),
        bid_mean_initial=rate(market_rates, "bid_mean_initial"),
        bid_std=rate(market_rates, "bid_std"),
        num_simulations=num_simulations,
        seed=seed,
        sorteio_share=sorteio_share,
    )


def fluxo_consorcio(sim, bid_amount: float, months: int) -> List[float]:
    """Parcelas do grupo, com o lance abatido no mês esperado de contemplação."""
    cashflows = [-sim.monthly_payment] * months
    expected_month = sim.contemplation_month_expected
    if expected_month < len(cashflows) and bid_amount > 0:
        cashflows[expected_month] -= bid_amount
    return cashflows
