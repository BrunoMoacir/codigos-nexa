"""
app/architect/simulators/macro_scenario.py
Simulação de cenários macroeconômicos correlacionados via VAR(1).

Parâmetros calibrados com dados históricos BCB 2015-2025.
Sem statsmodels — VAR(1) implementado diretamente com numpy + Cholesky.

Variáveis simuladas (taxas mensais):
  [0] selic       — Selic over / CDI
  [1] ipca        — IPCA mensal
  [2] appreciation — valorização do ativo (imóvel FIPE-ZAP)
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

# ─── Parâmetros macroeconômicos históricos brasileiros ────────────────────────
# Médias anuais (2015-2025) convertidas para mensais internamente.
_SELIC_MU_ANNUAL = 0.1200   # 12% a.a.
_IPCA_MU_ANNUAL  = 0.0500   #  5% a.a. — meta BCB
_APPR_MU_ANNUAL  = 0.0600   #  6% a.a. — valorização FIPE-ZAP imóvel


def _to_monthly(r_annual: float) -> float:
    return (1 + r_annual) ** (1 / 12) - 1


_MU = np.array([
    _to_monthly(_SELIC_MU_ANNUAL),
    _to_monthly(_IPCA_MU_ANNUAL),
    _to_monthly(_APPR_MU_ANNUAL),
])

# Persistência VAR(1) com efeitos cruzados calibrados (BCB 2015-2025):
#   Selic é exógena (política monetária); IPCA responde à Selic defasada (+8%);
#   apreciação responde negativamente à Selic (-10%) e positivamente ao IPCA (+15%).
_A = np.array([
    [ 0.92,  0.00,  0.00],
    [ 0.08,  0.85,  0.00],
    [-0.10,  0.15,  0.72],
])

# Covariância dos resíduos (mensal).
# Sinais: Selic ↑ → IPCA acompanha (+), Selic ↑ → apreciação cai (−).
#
# A variância da Selic era 1.5e-5 (σ = 0,387 p.p./mês), que num AR(1) com
# persistência 0,92 implica desvio ESTACIONÁRIO de 0,99 p.p./mês — três vezes
# o que a série real mostra. Consequência: 16% dos sorteios caíam abaixo de
# zero e eram truncados, empurrando a média simulada de 12% para 15% a.a.
#
# Recalibrado com a própria série do BCB (SGS 4390, Selic over mensal,
# 127 meses de 2016 a 2026): desvio estacionário observado de 0,3298 p.p./mês
# → σ do choque = 0,3298 × √(1 − 0,92²) = 0,1293 p.p./mês → variância 1,67e-6.
#
# A linha/coluna da Selic é escalada pelo mesmo fator (d = 0,334) para
# PRESERVAR as correlações com IPCA e apreciação — é Σ' = D·Σ·D com
# D = diag(d, 1, 1), o que também mantém a matriz positiva-definida para o
# Cholesky.
_SIGMA_E = np.array([
    [ 1.67e-6,  1.34e-6, -5.01e-7],
    [ 1.34e-6,  7.0e-6,   3.0e-6 ],
    [-5.01e-7,  3.0e-6,   2.0e-5 ],
])

_RATE_MIN = 0.0
_RATE_MAX = 0.05   # ~80% a.a. — teto para clamp


# ─── Geração de trajetórias ───────────────────────────────────────────────────

class MacroPaths:
    """Trajetórias macroeconômicas: arrays (n_sims, n_months) de taxas mensais."""

    __slots__ = ("selic", "ipca", "appreciation")

    def __init__(
        self,
        selic: np.ndarray,
        ipca: np.ndarray,
        appreciation: np.ndarray,
    ) -> None:
        self.selic        = selic
        self.ipca         = ipca
        self.appreciation = appreciation


# Piso para variáveis que PODEM ser negativas (deflação, desvalorização).
# −5% a.m. é folgado: o pior mês de deflação da série é −0,68% (ago/1998).
_RATE_MIN_SIGNED = -0.05


def generate_macro_paths(
    n_sims: int,
    n_months: int,
    initial_selic_annual: float,
    initial_ipca_annual: float  = _IPCA_MU_ANNUAL,
    initial_appr_annual: float  = _APPR_MU_ANNUAL,
    seed: Optional[int]         = None,
) -> MacroPaths:
    """
    VAR(1): y_t = μ + A*(y_{t-1} − μ) + L*ε_t,  ε_t ~ N(0, I_3).

    L = cholesky(_SIGMA_E) garante que os resíduos respeitem as correlações
    históricas entre Selic, IPCA e valorização do ativo.
    """
    rng = np.random.default_rng(seed)
    L = np.linalg.cholesky(_SIGMA_E)

    y0 = np.array([
        _to_monthly(initial_selic_annual),
        _to_monthly(initial_ipca_annual),
        _to_monthly(initial_appr_annual),
    ])

    # Todos os choques de uma vez: (n_months, n_sims, 3)
    z      = rng.standard_normal((n_months, n_sims, 3))
    shocks = z @ L.T  # correlações via Cholesky

    paths  = np.empty((n_months, n_sims, 3))
    y_prev = np.broadcast_to(y0, (n_sims, 3)).copy()

    for t in range(n_months):
        y_t = _MU + (y_prev - _MU) @ _A.T + shocks[t]
        paths[t] = y_t
        # O ESTADO segue sem clamp de propósito.
        #
        # Clampando dentro da recursão, o valor truncado realimentava o passo
        # seguinte e o viés COMPUNHA: o piso em 0 prendia 7% da Selic, 11,6%
        # do IPCA e 14,9% da valorização, enquanto o teto de 5% a.m. nunca era
        # tocado. O processo "com reversão à média de 12%" derivava para 15%
        # (ano 1: 12,9% → ano 10: 15,2%), e o IPCA de 5% para 8,2%.
        #
        # Sem clamp no estado, a reversão à média funciona: E[y_t] → μ.
        y_prev = y_t

    selic = paths[:, :, 0].T
    ipca  = paths[:, :, 1].T
    appr  = paths[:, :, 2].T

    # Saneamento aplicado só na SAÍDA, e por variável — cada uma tem domínio
    # econômico próprio:
    #   • Selic: taxa nominal de política monetária não é negativa;
    #   • IPCA: deflação existe (2017 teve meses negativos) — piso livre;
    #   • valorização: imóvel e veículo caem de preço — piso livre.
    # Antes as três eram truncadas em 0, o que além do viés proibia deflação
    # e desvalorização, dois fenômenos reais que a simulação precisa cobrir.
    selic = np.clip(selic, 0.0, _RATE_MAX)
    ipca  = np.clip(ipca,  _RATE_MIN_SIGNED, _RATE_MAX)
    appr  = np.clip(appr,  _RATE_MIN_SIGNED, _RATE_MAX)

    return MacroPaths(
        selic        = selic,  # → (n_sims, n_months)
        ipca         = ipca,
        appreciation = appr,
    )


# ─── Distribuição de NPVs por estratégia ─────────────────────────────────────

class StrategyDistribution:
    """Estatísticas de NPV sob N cenários macroeconômicos."""

    __slots__ = ("npv_p10", "npv_p50", "npv_p90", "cvar_95")

    def __init__(
        self,
        npv_p10: float,
        npv_p50: float,
        npv_p90: float,
        cvar_95: float,
    ) -> None:
        self.npv_p10 = npv_p10
        self.npv_p50 = npv_p50
        self.npv_p90 = npv_p90
        self.cvar_95 = cvar_95


def run_macro_simulation(
    n_sims: int,
    initial_selic_annual: float,
    financing_cashflows: Optional[List[float]],
    financing_months: int,
    save_monthly: float,
    target_amount: float,
    down_payment: float,
    consortium_months: Optional[int]              = None,
    consortium_admin_reserve: float               = 0.19,
    consortium_expected_contemplation: Optional[int] = None,
    invest_factor: float                          = 0.85,
    seed: Optional[int]                           = None,
) -> Tuple[Dict[str, StrategyDistribution], Dict[str, float], Dict[str, Dict[str, str]]]:
    """
    Simula N cenários macroeconômicos correlacionados e retorna:
      - distributions: estatísticas de NPV (P10/P50/P90 + CVaR95) por estratégia
      - prob_best: P(esta estratégia tem o melhor NPV) — soma 1.0
      - ssd_matrix: dominância SSD par a par ("dominates"/"dominated"/"inconclusive")

    Args:
        n_sims:                            número de trajetórias simuladas
        initial_selic_annual:              Selic atual (decimal anual, ex: 0.1475)
        financing_cashflows:               [-entrada, -p1, ..., -pN] do financiamento
        financing_months:                  prazo do financiamento (usado como horizonte)
        save_monthly:                      depósito mensal da estratégia Poupar/Investir
        target_amount:                     valor do bem (R$)
        down_payment:                      entrada (R$)
        consortium_months:                 duração do grupo de consórcio
        consortium_admin_reserve:          taxa adm + fundo reserva (ex: 0.19 = 19%)
        consortium_expected_contemplation: mês esperado de contemplação (do Monte Carlo)
        seed:                              semente para reprodutibilidade

    Returns:
        (distributions, prob_best, ssd_matrix)
    """
    n_months = max(
        financing_months,
        consortium_months or 0,
        120,  # mínimo de 10 anos para cobertura do SAVE_INVEST
    )

    paths = generate_macro_paths(
        n_sims, n_months, initial_selic_annual, seed=seed
    )

    raw = _compute_raw_npvs(
        paths               = paths,
        fin_cashflows       = financing_cashflows,
        save_monthly        = save_monthly,
        target_amount       = target_amount,
        down_payment        = down_payment,
        n_months            = n_months,
        consortium_months   = consortium_months,
        consortium_ar       = consortium_admin_reserve,
        expected_contemp    = consortium_expected_contemplation,
        invest_factor       = invest_factor,
    )

    distributions = {k: _stats(v) for k, v in raw.items()}
    prob_best     = _compute_prob_best(raw)
    ssd_matrix    = _compute_ssd_matrix(raw)
    return distributions, prob_best, ssd_matrix


# ─── Cálculo de NPVs por trajetória (vetorizado) ─────────────────────────────

def _compute_raw_npvs(
    paths: MacroPaths,
    fin_cashflows: Optional[List[float]],
    save_monthly: float,
    target_amount: float,
    down_payment: float,
    n_months: int,
    consortium_months: Optional[int],
    consortium_ar: float,
    expected_contemp: Optional[int],
    invest_factor: float = 0.85,
) -> Dict[str, np.ndarray]:
    raw: Dict[str, np.ndarray] = {}

    if fin_cashflows is not None:
        raw["FINANCING"] = _npv_fixed(np.array(fin_cashflows, dtype=float), paths.selic)

    raw["SAVE_INVEST"] = _npv_save_invest(
        save_monthly, target_amount, down_payment, paths.selic, invest_factor
    )

    if consortium_months is not None and expected_contemp is not None:
        raw["CONSORTIUM"] = _npv_consortium(
            target_amount,
            consortium_months,
            consortium_ar,
            down_payment,
            expected_contemp,
            paths.selic,
            paths.ipca,
        )

    return raw


def _npv_fixed(cashflows: np.ndarray, selic: np.ndarray) -> np.ndarray:
    """
    NPV de fluxos nominais fixos (CF_0 + CF_1..n) descontados pela trajetória Selic.

    Captura o risco de taxa: quando a Selic cai, o custo presente do financiamento
    fixo *aumenta* (desconto menor → VP das parcelas mais alto, mais negativo).
    """
    n    = min(cashflows.shape[0] - 1, selic.shape[1])
    cum  = np.cumprod(1 + selic[:, :n], axis=1)           # (n_sims, n)
    pv   = cashflows[1:n + 1][np.newaxis, :] / cum        # (n_sims, n)
    return cashflows[0] + np.sum(pv, axis=1)              # (n_sims,)


def _npv_save_invest(
    monthly: float,
    target: float,
    down_payment: float,
    selic: np.ndarray,
    invest_factor: float = 0.85,
) -> np.ndarray:
    """
    NPV de SAVE_INVEST com acumulação tracking CDI ajustado ao perfil de risco.

    O número de meses até atingir o target varia por trajetória:
      alta Selic → acumulação mais rápida → menos meses → NPV mais alto.

    invest_factor = taxa_investimento_usuario / selic_anual — captura o custo
    de oportunidade real do usuário, não apenas CDI × 0.85 genérico.

    Fórmula vetorizada (fim de período):
      FV_t = P_t * (down_payment + monthly * Σ_{k=1}^t 1/P_k)
      onde P_t = Π_{τ=1}^t (1 + invest_rate_τ)
    """
    n_sims, n = selic.shape
    invest    = selic * invest_factor                      # custo de oportunidade real

    cum_inv   = np.cumprod(1 + invest, axis=1)            # P_t (n_sims, n)
    cum_sel   = np.cumprod(1 + selic,  axis=1)            # desconto (n_sims, n)

    inv_p     = 1.0 / cum_inv                             # 1/P_k (n_sims, n)
    cum_sum   = np.cumsum(inv_p, axis=1)                  # Σ 1/P_k (n_sims, n)
    fv        = cum_inv * (down_payment + monthly * cum_sum)  # (n_sims, n)

    reached   = fv >= target
    first_t   = np.where(reached.any(axis=1), np.argmax(reached, axis=1), n - 1)

    t_idx = np.arange(n)
    mask  = t_idx[np.newaxis, :] <= first_t[:, np.newaxis]    # (n_sims, n)
    pv_d  = monthly / cum_sel                                  # PV de cada depósito

    return -down_payment - np.sum(pv_d * mask, axis=1)


def _npv_consortium(
    target: float,
    cons_months: int,
    admin_reserve: float,
    down_payment: float,
    expected_contemplation: int,
    selic: np.ndarray,
    ipca: np.ndarray,
) -> np.ndarray:
    """
    NPV do consórcio com carta de crédito crescendo mensalmente pelo IPCA do path.

    Captura o risco de inflação: IPCA alto → carta mais cara → parcelas maiores
    → NPV mais negativo. Correlação positiva IPCA↑ / Selic↑ suaviza parcialmente
    (desconto também maior).
    """
    n_sims = selic.shape[0]
    n      = min(cons_months, selic.shape[1])

    # Carta de crédito no início de cada mês: cresce com o IPCA acumulado
    cum_ipca = np.cumprod(1 + ipca[:, :n], axis=1)           # (n_sims, n)
    letter   = target * np.hstack(
        [np.ones((n_sims, 1)), cum_ipca[:, :-1]]
    )                                                         # (n_sims, n)
    payments = letter * (1 + admin_reserve) / cons_months     # (n_sims, n)

    cum_sel  = np.cumprod(1 + selic[:, :n], axis=1)          # (n_sims, n)
    npv      = -np.sum(payments / cum_sel, axis=1)           # (n_sims,)

    # Lance no mês esperado de contemplação
    if down_payment > 0 and expected_contemplation < n:
        t    = min(expected_contemplation, n - 1)
        npv -= down_payment / cum_sel[:, t]

    return npv


# ─── Estatísticas ─────────────────────────────────────────────────────────────

def _stats(npvs: np.ndarray) -> StrategyDistribution:
    sorted_n = np.sort(npvs)
    tail     = max(1, int(0.05 * len(sorted_n)))
    return StrategyDistribution(
        npv_p10 = float(np.percentile(npvs, 10)),
        npv_p50 = float(np.percentile(npvs, 50)),
        npv_p90 = float(np.percentile(npvs, 90)),
        cvar_95 = float(np.mean(sorted_n[:tail])),
    )


def _compute_prob_best(npv_arrays: Dict[str, np.ndarray]) -> Dict[str, float]:
    """
    P(esta estratégia tem o melhor NPV) — maior NPV = menor custo presente.
    As probabilidades somam 1.0.
    """
    if not npv_arrays:
        return {}
    keys   = list(npv_arrays.keys())
    matrix = np.stack([npv_arrays[k] for k in keys], axis=1)  # (n_sims, K)
    best   = np.argmax(matrix, axis=1)
    n      = len(best)
    return {k: round(float(np.sum(best == i) / n), 4) for i, k in enumerate(keys)}


def _compute_ssd_matrix(
    npv_arrays: Dict[str, np.ndarray],
) -> Dict[str, Dict[str, str]]:
    """
    Dominância Estocástica de Segunda Ordem (SSD) par a par.

    ssd[A][B] = "dominates" | "dominated" | "inconclusive"

    A domina B em SSD quando ∫F_B(t)dt ≥ ∫F_A(t)dt para todo x — ou seja,
    A é preferível para QUALQUER agente avesso a risco, independente do grau
    de aversão. Isso captura o pior caso, não apenas a frequência de vitória.

    Implementação: grade comum de 500 pontos entre min e max dos dois arrays;
    integral acumulada de (F_B − F_A) deve ser ≥ 0 em todos os pontos (TOL=1e-4).
    """
    if not npv_arrays:
        return {}
    keys = list(npv_arrays.keys())
    TOL  = 1e-4
    sorted_arrays = {k: np.sort(v) for k, v in npv_arrays.items()}
    result: Dict[str, Dict[str, str]] = {}

    for ki in keys:
        row: Dict[str, str] = {}
        dist_a = sorted_arrays[ki]
        for kj in keys:
            if ki == kj:
                continue
            dist_b = sorted_arrays[kj]
            grid   = np.linspace(
                min(dist_a[0], dist_b[0]),
                max(dist_a[-1], dist_b[-1]),
                num=500,
            )
            cdf_a    = np.searchsorted(dist_a, grid, side="right") / len(dist_a)
            cdf_b    = np.searchsorted(dist_b, grid, side="right") / len(dist_b)
            step     = grid[1] - grid[0]
            integral = np.cumsum((cdf_b - cdf_a) * step)

            if np.all(integral >= -TOL):
                row[kj] = "dominates"
            elif np.all(integral <= TOL):
                row[kj] = "dominated"
            else:
                row[kj] = "inconclusive"
        result[ki] = row
    return result


__all__ = [
    "MacroPaths",
    "StrategyDistribution",
    "generate_macro_paths",
    "run_macro_simulation",
    "_compute_ssd_matrix",
]
