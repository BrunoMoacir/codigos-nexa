"""
app/architect/simulators/monte_carlo.py - Motor de Monte Carlo Genérico

Feature: F3 - Nexa Architect
Version: 2.0.0 (Fase 2)

Responsabilidade:
    Motor reutilizável de simulação probabilística via Monte Carlo.
    Usado por:
      - consortium.py: modelagem de contemplação
      - (Fase 3) sensitivity_analyzer.py: análise de sensibilidade

Decisões de design:
    - Sem numpy: usa apenas stdlib (random, statistics, math)
      → mantém consistência com a diretriz do strategy_engine
      → elimina dependência pesada para deploy
    - Seed opcional para reprodutibilidade em testes
    - Distribuições incluídas: normal, uniforme, log-normal
    - Funções auxiliares de probabilidade (P(X <= threshold), etc.)

Uso:
    from app.architect.simulators.monte_carlo import run_monte_carlo, sample_normal

    result = run_monte_carlo(minha_funcao_de_cenario, n_iterations=5000)
    print(result.mean, result.percentile_90)
"""

import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELO DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class MonteCarloResult:
    """
    Estatísticas agregadas de uma simulação de Monte Carlo.

    Todas as métricas derivam do conjunto de resultados das N iterações.

    Attributes:
        iterations:    Número de iterações executadas.
        mean:          Média dos resultados.
        median:        Mediana dos resultados (P50).
        std_dev:       Desvio padrão dos resultados.
        min_value:     Menor resultado observado.
        max_value:     Maior resultado observado.
        percentile_10: P10 — 10% dos resultados ficaram abaixo deste valor.
        percentile_25: P25 (1º quartil).
        percentile_75: P75 (3º quartil).
        percentile_90: P90.
        percentile_95: P95 — útil para cenários de risco.
    """

    iterations: int
    mean: float
    median: float
    std_dev: float
    min_value: float
    max_value: float
    percentile_10: float
    percentile_25: float
    percentile_75: float
    percentile_90: float
    percentile_95: float

    def to_dict(self) -> Dict:
        """Serializa para dict (uso em logs e API responses)."""
        return {
            "iterations":    self.iterations,
            "mean":          self.mean,
            "median":        self.median,
            "std_dev":       self.std_dev,
            "min_value":     self.min_value,
            "max_value":     self.max_value,
            "percentile_10": self.percentile_10,
            "percentile_25": self.percentile_25,
            "percentile_75": self.percentile_75,
            "percentile_90": self.percentile_90,
            "percentile_95": self.percentile_95,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MOTOR PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def run_monte_carlo(
    scenario_fn: Callable[[], float],
    n_iterations: int = 2000,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """
    Executa uma simulação de Monte Carlo chamando `scenario_fn` N vezes.

    Cada chamada a `scenario_fn` representa um cenário independente.
    A função deve ser autossuficiente: amostrar suas variáveis aleatórias
    internamente e retornar um único valor numérico de resultado.

    Args:
        scenario_fn:   Função sem argumentos que retorna um float (um cenário).
        n_iterations:  Número de iterações. Padrão: 2000.
                       >= 1000 para intervalos de confiança razoáveis.
                       >= 5000 para análises de risco de cauda (P95+).
        seed:          Semente aleatória opcional. Quando definida, a simulação
                       é determinística (mesmos resultados a cada execução).
                       Útil para testes e auditoria.

    Returns:
        MonteCarloResult com estatísticas completas da distribuição.

    Raises:
        ValueError: Se n_iterations < 1.
        RuntimeError: Se scenario_fn lançar exceção em todas as iterações.

    Example:
        >>> import random
        >>> def meu_cenario():
        ...     return random.gauss(100.0, 10.0)   # média 100, desvio 10
        >>> result = run_monte_carlo(meu_cenario, n_iterations=3000, seed=42)
        >>> print(f"Média: {result.mean:.2f}, P90: {result.percentile_90:.2f}")
        Média: 100.00, P90: 112.82
    """
    if n_iterations < 1:
        raise ValueError(f"n_iterations deve ser >= 1, recebido: {n_iterations}")

    if seed is not None:
        random.seed(seed)

    results: List[float] = []
    errors = 0

    for _ in range(n_iterations):
        try:
            results.append(float(scenario_fn()))
        except Exception:
            errors += 1

    if not results:
        raise RuntimeError(
            f"scenario_fn falhou em todas as {n_iterations} iterações "
            f"(errors={errors})."
        )

    return _aggregate(results, n_iterations)


def run_monte_carlo_batch(
    scenario_fn: Callable[[], float],
    n_iterations: int = 2000,
    seed: Optional[int] = None,
) -> tuple[MonteCarloResult, List[float]]:
    """
    Versão estendida de `run_monte_carlo` que também retorna os resultados brutos.

    Útil quando você precisa calcular probabilidades condicionais ou
    plotar histogramas após a simulação.

    Returns:
        (MonteCarloResult, raw_results): resultado agregado + lista de valores.

    Example:
        >>> result, raw = run_monte_carlo_batch(cenario, n_iterations=5000, seed=0)
        >>> p_under_threshold = probability_below(raw, threshold=90.0)
    """
    if n_iterations < 1:
        raise ValueError(f"n_iterations deve ser >= 1, recebido: {n_iterations}")

    if seed is not None:
        random.seed(seed)

    results = [float(scenario_fn()) for _ in range(n_iterations)]
    return _aggregate(results, n_iterations), results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES DE PROBABILIDADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def probability_below(values: List[float], threshold: float) -> float:
    """
    Calcula P(X <= threshold) a partir dos resultados brutos.

    Args:
        values:    Lista de resultados brutos de uma simulação.
        threshold: Valor limiar.

    Returns:
        Proporção de valores <= threshold. Em [0.0, 1.0].

    Example:
        >>> probability_below([1, 2, 3, 4, 5], threshold=3)
        0.6
    """
    if not values:
        return 0.0
    return sum(1 for v in values if v <= threshold) / len(values)


def probability_above(values: List[float], threshold: float) -> float:
    """
    Calcula P(X > threshold) a partir dos resultados brutos.

    Returns:
        Proporção de valores > threshold. Em [0.0, 1.0].
        Retorna 0.0 se `values` for vazio.
    """
    if not values:
        return 0.0
    return 1.0 - probability_below(values, threshold)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DISTRIBUIÇÕES PROBABILÍSTICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def sample_normal(mean: float, std: float) -> float:
    """
    Amostra da distribuição normal (gaussiana).

    Args:
        mean: Média da distribuição.
        std:  Desvio padrão (deve ser >= 0).

    Returns:
        Um valor amostrado.

    Example:
        >>> random.seed(42)
        >>> sample_normal(100.0, 10.0)
        104.83...
    """
    if std <= 0:
        return mean
    return random.gauss(mean, std)


def sample_uniform(low: float, high: float) -> float:
    """
    Amostra da distribuição uniforme contínua em [low, high].

    Args:
        low:  Limite inferior.
        high: Limite superior (deve ser > low).

    Returns:
        Um valor em [low, high].
    """
    if high <= low:
        return low
    return random.uniform(low, high)


def sample_lognormal(mu: float, sigma: float) -> float:
    """
    Amostra da distribuição log-normal com parâmetros mu e sigma
    da distribuição normal subjacente.

    Resulta em X = exp(N(mu, sigma)), sempre positivo.
    Valor esperado (média): exp(mu + sigma²/2).

    Útil para modelar: juros, lances em consórcio, valores de bens.

    Args:
        mu:    Parâmetro de localização da normal subjacente.
        sigma: Parâmetro de escala da normal subjacente (>= 0).

    Returns:
        Um valor positivo amostrado da log-normal.

    Example:
        >>> # Simular lance de consórcio (mean ~40%, std ~10%)
        >>> lance = sample_lognormal(mu=-0.92, sigma=0.25)  # aprox 40%
    """
    if sigma <= 0:
        return math.exp(mu)
    return math.exp(random.gauss(mu, sigma))


def clamp(value: float, lo: float, hi: float) -> float:
    """
    Limita `value` ao intervalo [lo, hi].

    Utilitário para clampar resultados de distribuições que podem
    extrapolar os limites do domínio do problema.

    Example:
        >>> clamp(1.25, 0.0, 1.0)
        1.0
        >>> clamp(-0.05, 0.0, 1.0)
        0.0
    """
    return max(lo, min(hi, value))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER INTERNO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _percentile(sorted_values: List[float], p: float) -> float:
    """
    Calcula o percentil `p` de uma lista já ordenada.

    Usa interpolação linear entre os dois vizinhos mais próximos
    (método "fraction" — compatível com numpy e pandas).

    Args:
        sorted_values: Lista de floats em ordem crescente.
        p:             Percentil em [0, 100].

    Returns:
        Valor do percentil.
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]

    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = lo + 1

    if hi >= n:
        return sorted_values[-1]

    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _aggregate(results: List[float], n_iterations: int) -> MonteCarloResult:
    """Calcula estatísticas sobre a lista de resultados brutos."""
    sorted_r = sorted(results)
    n = len(results)

    return MonteCarloResult(
        iterations=n_iterations,
        mean=round(statistics.mean(results), 6),
        median=round(statistics.median(sorted_r), 6),
        std_dev=round(statistics.stdev(results) if n > 1 else 0.0, 6),
        min_value=sorted_r[0],
        max_value=sorted_r[-1],
        percentile_10=round(_percentile(sorted_r, 10), 6),
        percentile_25=round(_percentile(sorted_r, 25), 6),
        percentile_75=round(_percentile(sorted_r, 75), 6),
        percentile_90=round(_percentile(sorted_r, 90), 6),
        percentile_95=round(_percentile(sorted_r, 95), 6),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    "MonteCarloResult",
    "run_monte_carlo",
    "run_monte_carlo_batch",
    "probability_below",
    "probability_above",
    "sample_normal",
    "sample_uniform",
    "sample_lognormal",
    "clamp",
]
