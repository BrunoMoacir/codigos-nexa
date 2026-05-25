"""
app/architect/calculators/consortium.py - Calculadora de Consórcio (Monte Carlo)

Feature: F3 - Nexa Architect
Version: 2.0.0

Responsabilidade:
Simular o comportamento de um grupo de consórcio para estimar:
1. Probabilidade de contemplação mensal (sorteio + lance).
2. Custo total esperado (considerando reajuste anual da carta e taxas).
3. Prazo médio de contemplação.
4. Comparação entre cenários com/sem lance.

Metodologia:
Utiliza Simulação de Monte Carlo para modelar os sorteios e a distribuição
de lances do grupo, gerando cenários probabilísticos.

Changelog v2.0.0 (melhorias de realismo):
- Reajuste anual da carta de crédito (INCC para imóvel, IPCA para veículo)
- Parcelas reajustadas proporcionalmente ao saldo remanescente
- Seed controlável para reprodutibilidade (testes e debugging)
- Decaimento exponencial de lances (mais realista que linear)
- Grupo parametrizável (tamanho, contemplados/mês)
- Cálculo de custo total real (nominal + reajuste)
- Percentis de contemplação (P25, P50, P75) + P10/P90
- compare_with_without_bid para análise de estratégia de lance
- Compatibilidade retroativa: campos total_cost e monthly_payment preservados
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import numpy as np


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ÍNDICES DE REAJUSTE PADRÃO (anuais, em decimal)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Valores médios históricos recentes (2020-2025).
# Em produção, substituir por dados reais via bacen_connector.py.

ADJUSTMENT_INDICES = {
    "vehicle":    0.045,   # IPCA médio ~4,5% a.a.
    "property":   0.070,   # INCC médio ~7,0% a.a.
    "motorcycle": 0.045,   # IPCA
    "truck":      0.050,   # IPCA + componente setorial
    "appliance":  0.045,   # IPCA
    "service":    0.060,   # IPCA serviços (~6%)
    "other":      0.045,   # IPCA padrão
}


@dataclass
class ConsortiumResult:
    """
    Resultado da simulação de consórcio.

    Campos retrocompatíveis (v1 → v2):
        total_cost:      Custo total real com reajuste (alias de total_cost_real)
        monthly_payment: Parcela do mês 1 (alias de monthly_payment_initial)

    Campos novos (v2):
        total_cost_nominal:          Custo sem reajuste (base de comparação)
        total_cost_real:             Custo com reajuste anual capitalizado
        monthly_payment_initial:     Parcela mês 1
        monthly_payment_final:       Parcela estimada no mês final
        payment_schedule_summary:    Evolução das parcelas por ano
        letter_value_initial/final:  Carta antes e depois dos reajustes
        contemplation_percentiles:   P10, P25, P50, P75, P90
        annual_adjustment_rate:      Taxa de reajuste aplicada
        asset_type:                  Tipo de bem (vehicle, property, …)
        group_size:                  Tamanho do grupo simulado
    """
    # Contemplação
    contemplation_month_expected: int          # Mediana (P50)
    contemplation_percentiles: Dict[str, int]  # p10, p25, p50, p75, p90
    contemplation_probability: Dict[str, float]

    # Custos (retrocompat: total_cost e monthly_payment mantidos)
    total_cost_nominal: float
    total_cost_real: float
    total_cost: float                           # = total_cost_real (v1 compat)
    monthly_payment_initial: float
    monthly_payment_final: float
    monthly_payment: float                      # = monthly_payment_initial (v1 compat)
    payment_schedule_summary: List[Dict]

    # Taxas
    admin_fee_total: float
    reserve_fund_total: float

    # Lance
    bid_amount_needed: float

    # Carta de crédito
    letter_value_initial: float
    letter_value_final: float
    annual_adjustment_rate: float
    asset_type: str

    # Meta
    scenarios: int
    group_size: int

    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_consortium_metrics(
    letter_value: float,
    months: int,
    admin_rate: float,
    reserve_fund_rate: float = 0.0,
    bid_strategy: str = "fixed",
    bid_amount: float = 0.0,
    asset_type: str = "vehicle",
    annual_adjustment_rate: Optional[float] = None,
    group_size: int = 100,
    contemplated_per_month: int = 2,
    num_simulations: int = 2000,
    seed: Optional[int] = None,
    bid_mean_initial: float = 0.35,
    bid_std: float = 0.12,
) -> ConsortiumResult:
    """
    Simula um grupo de consórcio para estimar custos e prazos.

    Args:
        letter_value:           Valor da carta de crédito (R$)
        months:                 Prazo do grupo (meses)
        admin_rate:             Taxa de administração total (ex: 0.17 = 17%)
        reserve_fund_rate:      Fundo de reserva total (ex: 0.02 = 2%)
        bid_strategy:           'fixed' (lance embutido) ou 'free' (lance livre)
        bid_amount:             Valor para lance livre (bid_strategy='free')
        asset_type:             Tipo de bem — define o índice de reajuste padrão.
                                Valores: 'vehicle', 'property', 'motorcycle',
                                'truck', 'appliance', 'service', 'other'
        annual_adjustment_rate: Taxa de reajuste anual (decimal).
                                Se None, usa o padrão do asset_type.
        group_size:             Número de participantes no grupo (10–999)
        contemplated_per_month: Total de contemplados por assembleia (sorteio + lances)
        num_simulations:        Iterações do Monte Carlo
        seed:                   Seed para reprodutibilidade (None = aleatório)

    Returns:
        ConsortiumResult com estatísticas, intervalos e cronograma de parcelas.
    """
    if letter_value <= 0:
        raise ValueError("Valor da carta deve ser positivo")
    if months <= 0:
        raise ValueError("Prazo deve ser positivo")
    if admin_rate < 0:
        raise ValueError("Taxa de administração não pode ser negativa")
    if reserve_fund_rate < 0:
        raise ValueError("Fundo de reserva não pode ser negativo")
    if group_size < 10:
        raise ValueError("Grupo deve ter pelo menos 10 participantes")
    if contemplated_per_month < 1:
        raise ValueError("Deve haver pelo menos 1 contemplado por mês")

    # ── Índice de reajuste ────────────────────────────────────────────────────
    adj_rate = (
        annual_adjustment_rate
        if annual_adjustment_rate is not None
        else ADJUSTMENT_INDICES.get(asset_type, ADJUSTMENT_INDICES["other"])
    )
    monthly_adj_rate = (1 + adj_rate) ** (1 / 12) - 1

    # ── Gerador reproduzível ──────────────────────────────────────────────────
    rng = np.random.default_rng(seed)

    # ── Cronograma de parcelas com reajuste ───────────────────────────────────
    schedule = _calculate_payment_schedule(
        letter_value=letter_value,
        months=months,
        admin_rate=admin_rate,
        reserve_fund_rate=reserve_fund_rate,
        monthly_adj_rate=monthly_adj_rate,
    )

    total_cost_nominal = letter_value * (1 + admin_rate + reserve_fund_rate)
    total_cost_real = sum(p["payment"] for p in schedule)
    monthly_payment_initial = schedule[0]["payment"]
    monthly_payment_final = schedule[-1]["payment"]
    admin_fee_total = sum(p["admin_portion"] for p in schedule)
    reserve_fund_total = sum(p["reserve_portion"] for p in schedule)
    letter_value_final = schedule[-1]["letter_value_adjusted"]

    # ── Lance efetivo ─────────────────────────────────────────────────────────
    if bid_strategy == "fixed":
        # Lance embutido: usa ~25% da carta como lance (faixa real ABAC: 10–30%)
        effective_bid = letter_value * 0.25
    else:
        effective_bid = bid_amount

    bid_ratio = effective_bid / letter_value if letter_value > 0 else 0.0

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    contemplation_months = np.empty(num_simulations, dtype=np.int32)
    for i in range(num_simulations):
        contemplation_months[i] = _simulate_single_run(
            months=months,
            user_bid_ratio=bid_ratio,
            group_size=max(1, group_size),
            contemplated_per_month=contemplated_per_month,
            rng=rng,
            bid_mean_initial=bid_mean_initial,
            bid_std=bid_std,
        )

    # ── Estatísticas ──────────────────────────────────────────────────────────
    expected_month = int(np.median(contemplation_months))
    percentiles = {
        "p10": int(np.percentile(contemplation_months, 10)),
        "p25": int(np.percentile(contemplation_months, 25)),
        "p50": int(np.percentile(contemplation_months, 50)),
        "p75": int(np.percentile(contemplation_months, 75)),
        "p90": int(np.percentile(contemplation_months, 90)),
    }

    probs: Dict[str, float] = {}
    for label, cutoff in [("6m", 6), ("12m", 12), ("24m", 24), ("half_term", months // 2)]:
        if cutoff <= months:
            probs[label] = round(float(np.sum(contemplation_months <= cutoff) / num_simulations), 4)

    return ConsortiumResult(
        contemplation_month_expected=expected_month,
        contemplation_percentiles=percentiles,
        contemplation_probability=probs,
        total_cost_nominal=round(total_cost_nominal, 2),
        total_cost_real=round(total_cost_real, 2),
        total_cost=round(total_cost_real, 2),              # v1 compat
        monthly_payment_initial=round(monthly_payment_initial, 2),
        monthly_payment_final=round(monthly_payment_final, 2),
        monthly_payment=round(monthly_payment_initial, 2), # v1 compat
        payment_schedule_summary=_summarize_by_year(schedule),
        admin_fee_total=round(admin_fee_total, 2),
        reserve_fund_total=round(reserve_fund_total, 2),
        bid_amount_needed=round(effective_bid, 2),
        letter_value_initial=letter_value,
        letter_value_final=round(letter_value_final, 2),
        annual_adjustment_rate=adj_rate,
        asset_type=asset_type,
        scenarios=num_simulations,
        group_size=group_size,
    )


def _calculate_payment_schedule(
    letter_value: float,
    months: int,
    admin_rate: float,
    reserve_fund_rate: float,
    monthly_adj_rate: float,
) -> List[Dict]:
    """
    Gera o cronograma mensal de parcelas com reajuste da carta.

    Funcionamento:
    - A carta de crédito é reajustada mensalmente pelo índice contratual
      (INCC para imóvel, IPCA para veículo, etc.)
    - A parcela de cada mês = carta_reajustada × (1 + admin + reserva) / prazo_total
    - Resultado: parcelas sobem ao longo do grupo, refletindo a realidade do mercado

    Args:
        letter_value:      Valor inicial da carta (R$)
        months:            Prazo total (meses)
        admin_rate:        Taxa de administração (decimal)
        reserve_fund_rate: Fundo de reserva (decimal)
        monthly_adj_rate:  Taxa mensal de reajuste (derivada da anual composta)

    Returns:
        Lista de dicts com detalhes de cada parcela mensal.
    """
    total_rate = admin_rate + reserve_fund_rate
    current_letter = letter_value
    schedule = []

    for month in range(1, months + 1):
        if month > 1:
            current_letter *= (1 + monthly_adj_rate)

        payment = current_letter * (1 + total_rate) / months
        schedule.append({
            "month": month,
            "payment": round(payment, 2),
            "amort_portion": round(current_letter / months, 2),
            "admin_portion": round(current_letter * admin_rate / months, 2),
            "reserve_portion": round(current_letter * reserve_fund_rate / months, 2),
            "letter_value_adjusted": round(current_letter, 2),
        })

    return schedule


def _summarize_by_year(schedule: List[Dict]) -> List[Dict]:
    """Resume o cronograma de pagamentos por ano para exibição."""
    summary = []
    year_payments: List[float] = []
    current_year = 1

    for entry in schedule:
        year_payments.append(entry["payment"])
        if len(year_payments) == 12 or entry["month"] == len(schedule):
            summary.append({
                "year": current_year,
                "avg_monthly_payment": round(sum(year_payments) / len(year_payments), 2),
                "total_paid_year": round(sum(year_payments), 2),
                "letter_value_at_year_end": entry["letter_value_adjusted"],
                "months_in_year": len(year_payments),
            })
            year_payments = []
            current_year += 1

    return summary


def _simulate_single_run(
    months: int,
    user_bid_ratio: float,
    group_size: int,
    contemplated_per_month: int,
    rng: np.random.Generator,
    bid_mean_initial: float = 0.35,
    bid_std: float = 0.12,
) -> int:
    """
    Executa uma única trajetória do usuário no grupo de consórcio.

    Modelo de assembleia mensal:
    1. Sorteio: 1 contemplado aleatório (probabilidade = 1 / restantes)
    2. Lances: (contemplated_per_month - 1) vagas disputadas por lance
       - Lances do grupo seguem log-normal (cauda direita realista)
       - Decaimento exponencial da média: 35% no mês 1 → ~5% no final
         (half-life = 30% do prazo — lances agressivos concentram-se no início)
       - Usuário ganha se seu lance >= menor bid vencedor do mês

    Args:
        months:                 Prazo total
        user_bid_ratio:         Lance do usuário / carta (0.0–1.0)
        group_size:             Participantes iniciais
        contemplated_per_month: Total de contemplados por assembleia
        rng:                    Gerador numpy para reprodutibilidade

    Returns:
        Mês da contemplação (1 … months). Retorna `months` se não contemplado.
    """
    remaining = group_size

    # Decaimento exponencial: mean(t) = mean_0 * exp(-λ * t)
    # λ = ln(2) / (half_life * months)  →  λ torna a média 50% menor no half_life
    half_life_fraction = 0.30
    decay_lambda = np.log(2) / (half_life_fraction * months)

    for month in range(1, months + 1):
        if remaining <= 0:
            return month

        # ── Sorteio ──────────────────────────────────────────────────────────
        if rng.random() < (1.0 / remaining):
            return month
        remaining -= 1

        if remaining <= 0:
            return month

        # ── Lances ───────────────────────────────────────────────────────────
        lance_slots = min(contemplated_per_month - 1, remaining)

        if lance_slots > 0 and user_bid_ratio > 0:
            current_mean = bid_mean_initial * np.exp(-decay_lambda * month)

            if current_mean > 0.01:
                # Log-normal: garantia de valores positivos e cauda longa à direita
                sigma_ln = np.sqrt(np.log(1 + (bid_std / current_mean) ** 2))
                mu_ln = np.log(current_mean) - 0.5 * sigma_ln ** 2
                group_bids = rng.lognormal(mu_ln, sigma_ln, size=remaining)
                group_bids = np.clip(group_bids, 0.0, 1.0)
            else:
                # Lances simbólicos no final do grupo
                group_bids = rng.uniform(0.0, 0.05, size=remaining)

            # Os `lance_slots` maiores lances vencem; threshold = menor deles
            top_bids_sorted = np.partition(group_bids, -lance_slots)[-lance_slots:]
            winning_threshold = float(np.min(top_bids_sorted))

            if user_bid_ratio >= winning_threshold:
                return month

        remaining -= lance_slots

    return months


def compare_with_without_bid(
    letter_value: float,
    months: int,
    admin_rate: float,
    bid_amount: float,
    asset_type: str = "vehicle",
    reserve_fund_rate: float = 0.0,
    annual_adjustment_rate: Optional[float] = None,
    group_size: int = 100,
    contemplated_per_month: int = 2,
    num_simulations: int = 2000,
    seed: Optional[int] = None,
) -> Dict[str, ConsortiumResult]:
    """
    Compara cenários com lance livre vs sem lance (apenas sorteio).

    Útil para o agente responder: "Vale a pena dar lance de R$ X?"

    Args:
        letter_value:           Valor da carta
        months:                 Prazo do grupo
        admin_rate:             Taxa de administração
        bid_amount:             Valor do lance livre a comparar
        asset_type:             Tipo de bem
        reserve_fund_rate:      Fundo de reserva
        annual_adjustment_rate: Taxa de reajuste (None = padrão do tipo)
        group_size:             Tamanho do grupo
        contemplated_per_month: Contemplados por assembleia
        num_simulations:        Iterações Monte Carlo
        seed:                   Seed base para reprodutibilidade

    Returns:
        Dict com "with_bid" e "without_bid" (dois ConsortiumResult).

    Example:
        >>> comp = compare_with_without_bid(
        ...     letter_value=60000, months=72, admin_rate=0.18,
        ...     bid_amount=15000, seed=42
        ... )
        >>> comp["with_bid"].contemplation_month_expected <= \\
        ...     comp["without_bid"].contemplation_month_expected
        True
    """
    # Seeds derivadas independentes para cada cenário
    seed_with = seed
    seed_without = (seed + 1_000_000) if seed is not None else None

    common_kwargs = dict(
        letter_value=letter_value,
        months=months,
        admin_rate=admin_rate,
        reserve_fund_rate=reserve_fund_rate,
        bid_strategy="free",
        asset_type=asset_type,
        annual_adjustment_rate=annual_adjustment_rate,
        group_size=group_size,
        contemplated_per_month=contemplated_per_month,
        num_simulations=num_simulations,
    )

    return {
        "with_bid": calculate_consortium_metrics(**common_kwargs, bid_amount=bid_amount, seed=seed_with),
        "without_bid": calculate_consortium_metrics(**common_kwargs, bid_amount=0.0, seed=seed_without),
    }


__all__ = [
    "calculate_consortium_metrics",
    "compare_with_without_bid",
    "ConsortiumResult",
    "ADJUSTMENT_INDICES",
]
