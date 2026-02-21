"""
tests/architect/test_monte_carlo.py - Testes do Motor de Monte Carlo (Fase 2)

COMO RODAR:
    cd backend
    pytest tests/architect/test_monte_carlo.py -v
"""

import math
import random
import statistics

import pytest

from app.architect.simulators.monte_carlo import (
    MonteCarloResult,
    clamp,
    probability_above,
    probability_below,
    run_monte_carlo,
    run_monte_carlo_batch,
    sample_lognormal,
    sample_normal,
    sample_uniform,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def result_normal_100_10() -> MonteCarloResult:
    return run_monte_carlo(lambda: sample_normal(100.0, 10.0), n_iterations=5000, seed=42)


@pytest.fixture
def result_uniform_0_1() -> MonteCarloResult:
    return run_monte_carlo(lambda: sample_uniform(0.0, 1.0), n_iterations=5000, seed=0)


# ── MonteCarloResult ─────────────────────────────────────────────────────────


class TestMonteCarloResult:

    def test_to_dict_tem_11_campos(self, result_normal_100_10):
        assert len(result_normal_100_10.to_dict()) == 11

    def test_to_dict_campos_esperados(self, result_normal_100_10):
        campos = {
            "iterations", "mean", "median", "std_dev",
            "min_value", "max_value",
            "percentile_10", "percentile_25",
            "percentile_75", "percentile_90", "percentile_95",
        }
        assert set(result_normal_100_10.to_dict().keys()) == campos

    def test_to_dict_valores_sao_numericos(self, result_normal_100_10):
        for key, val in result_normal_100_10.to_dict().items():
            assert isinstance(val, (int, float)), f"{key} deve ser numérico"

    def test_min_menor_que_max(self, result_normal_100_10):
        r = result_normal_100_10
        assert r.min_value < r.max_value

    def test_percentis_ordenados(self, result_normal_100_10):
        r = result_normal_100_10
        assert r.percentile_10 <= r.percentile_25 <= r.median
        assert r.median <= r.percentile_75 <= r.percentile_90 <= r.percentile_95

    def test_iterations_correto(self):
        result = run_monte_carlo(lambda: 1.0, n_iterations=300, seed=1)
        assert result.iterations == 300


# ── run_monte_carlo ───────────────────────────────────────────────────────────


class TestRunMonteCarlo:

    def test_retorna_monte_carlo_result(self, result_normal_100_10):
        assert isinstance(result_normal_100_10, MonteCarloResult)

    def test_media_normal_100_10(self, result_normal_100_10):
        assert 98.0 <= result_normal_100_10.mean <= 102.0

    def test_desvio_normal_100_10(self, result_normal_100_10):
        assert 9.0 <= result_normal_100_10.std_dev <= 11.0

    def test_mediana_proxima_da_media_normal(self, result_normal_100_10):
        diff = abs(result_normal_100_10.mean - result_normal_100_10.median)
        assert diff < 2.0

    def test_seed_deterministico(self):
        fn = lambda: sample_normal(50.0, 5.0)
        r1 = run_monte_carlo(fn, n_iterations=1000, seed=99)
        r2 = run_monte_carlo(fn, n_iterations=1000, seed=99)
        assert r1.mean == r2.mean and r1.std_dev == r2.std_dev

    def test_seeds_diferentes_resultados_diferentes(self):
        r1 = run_monte_carlo(lambda: sample_normal(0.0, 1.0), n_iterations=200, seed=1)
        r2 = run_monte_carlo(lambda: sample_normal(0.0, 1.0), n_iterations=200, seed=2)
        assert r1.mean != r2.mean

    def test_valor_constante_std_zero(self):
        result = run_monte_carlo(lambda: 42.0, n_iterations=100, seed=0)
        assert result.mean == 42.0
        assert result.std_dev == 0.0
        assert result.min_value == result.max_value == 42.0

    def test_raises_para_n_iterations_zero(self):
        with pytest.raises(ValueError, match="n_iterations"):
            run_monte_carlo(lambda: 1.0, n_iterations=0)

    def test_raises_para_n_iterations_negativo(self):
        with pytest.raises(ValueError):
            run_monte_carlo(lambda: 1.0, n_iterations=-10)

    def test_runtime_error_quando_funcao_sempre_falha(self):
        def sempre_falha():
            raise RuntimeError("erro simulado")
        with pytest.raises(RuntimeError, match="falhou em todas"):
            run_monte_carlo(sempre_falha, n_iterations=10)

    def test_uma_iteracao_funciona(self):
        result = run_monte_carlo(lambda: 7.0, n_iterations=1)
        assert result.mean == 7.0 and result.iterations == 1


# ── run_monte_carlo_batch ─────────────────────────────────────────────────────


class TestRunMonteCarlobatch:

    def test_retorna_tupla_de_dois(self):
        result = run_monte_carlo_batch(lambda: 1.0, n_iterations=10)
        assert isinstance(result, tuple) and len(result) == 2

    def test_primeiro_e_monte_carlo_result(self):
        result, _ = run_monte_carlo_batch(lambda: 1.0, n_iterations=10)
        assert isinstance(result, MonteCarloResult)

    def test_segundo_e_lista(self):
        _, raw = run_monte_carlo_batch(lambda: 1.0, n_iterations=10)
        assert isinstance(raw, list)

    def test_lista_tem_tamanho_correto(self):
        _, raw = run_monte_carlo_batch(lambda: 1.0, n_iterations=500)
        assert len(raw) == 500

    def test_media_consistente_com_raw(self):
        result, raw = run_monte_carlo_batch(
            lambda: sample_normal(0.0, 1.0), n_iterations=2000, seed=5
        )
        assert abs(result.mean - statistics.mean(raw)) < 1e-4


# ── probability_below / probability_above ─────────────────────────────────────


class TestProbabilityFunctions:

    def test_probability_below_maximo_e_1(self):
        assert probability_below([1.0, 2.0, 3.0], threshold=3.0) == 1.0

    def test_probability_above_minimo_e_1(self):
        assert probability_above([1.0, 2.0, 3.0], threshold=0.9) == 1.0

    def test_probability_below_minimo_e_0(self):
        assert probability_below([1.0, 2.0, 3.0], threshold=0.5) == 0.0

    def test_complemento_soma_1(self):
        values = [float(i) for i in range(100)]
        p_below = probability_below(values, threshold=50.0)
        p_above = probability_above(values, threshold=50.0)
        assert abs(p_below + p_above - 1.0) < 1e-9

    def test_mediana_aprox_0_5_para_normal(self):
        _, raw = run_monte_carlo_batch(
            lambda: sample_normal(0.0, 1.0), n_iterations=5000, seed=42
        )
        p = probability_below(raw, threshold=0.0)
        assert 0.45 <= p <= 0.55

    def test_lista_vazia_retorna_zero(self):
        assert probability_below([], threshold=100.0) == 0.0
        assert probability_above([], threshold=0.0) == 0.0

    def test_um_elemento(self):
        assert probability_below([5.0], threshold=5.0) == 1.0
        assert probability_below([5.0], threshold=4.9) == 0.0


# ── Distribuições ─────────────────────────────────────────────────────────────


class TestDistribuicoes:

    # sample_normal
    def test_sample_normal_media_correta(self):
        random.seed(10)
        amostras = [sample_normal(200.0, 20.0) for _ in range(3000)]
        assert 196.0 <= statistics.mean(amostras) <= 204.0

    def test_sample_normal_std_zero_retorna_media(self):
        assert sample_normal(42.0, 0.0) == 42.0

    def test_sample_normal_retorna_float(self):
        assert isinstance(sample_normal(0.0, 1.0), float)

    # sample_uniform
    def test_sample_uniform_dentro_do_intervalo(self):
        random.seed(1)
        for _ in range(1000):
            v = sample_uniform(10.0, 20.0)
            assert 10.0 <= v <= 20.0

    def test_sample_uniform_high_igual_low_retorna_low(self):
        assert sample_uniform(5.0, 5.0) == 5.0

    def test_sample_uniform_high_menor_que_low_retorna_low(self):
        assert sample_uniform(10.0, 5.0) == 10.0

    def test_sample_uniform_media_central(self):
        random.seed(2)
        amostras = [sample_uniform(0.0, 100.0) for _ in range(5000)]
        assert 48.0 <= statistics.mean(amostras) <= 52.0

    # sample_lognormal
    def test_sample_lognormal_sempre_positivo(self):
        random.seed(3)
        for _ in range(500):
            assert sample_lognormal(0.0, 1.0) > 0.0

    def test_sample_lognormal_sigma_zero_retorna_exp_mu(self):
        v = sample_lognormal(mu=2.0, sigma=0.0)
        assert abs(v - math.exp(2.0)) < 1e-9

    def test_sample_lognormal_retorna_float(self):
        assert isinstance(sample_lognormal(0.0, 0.5), float)

    # clamp
    def test_clamp_dentro_do_intervalo(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_clamp_acima_do_maximo(self):
        assert clamp(1.5, 0.0, 1.0) == 1.0

    def test_clamp_abaixo_do_minimo(self):
        assert clamp(-0.1, 0.0, 1.0) == 0.0

    def test_clamp_nos_limites(self):
        assert clamp(0.0, 0.0, 1.0) == 0.0
        assert clamp(1.0, 0.0, 1.0) == 1.0


# ── Integração com consórcio ──────────────────────────────────────────────────


class TestIntegracaoConsorcio:
    """
    Verifica que run_monte_carlo modela corretamente a contemplação de consórcio.
    """

    def test_modelagem_contemplacao_retorna_meses_validos(self):
        def cenario():
            return float(random.randint(1, 72))
        result = run_monte_carlo(cenario, n_iterations=3000, seed=7)
        assert 1.0 <= result.min_value <= 72.0
        assert 1.0 <= result.max_value <= 72.0
        assert 33.0 <= result.mean <= 40.0  # Uniforme[1,72] → média ≈ 36.5

    def test_probabilidade_contemplacao_em_12_meses(self):
        """P(contemplação <= 12) com grupo de 200 e só sorteio ≈ 5.8%."""
        def cenario():
            for mes in range(1, 73):
                if random.random() < (1.0 / 200):
                    return float(mes)
            return 72.0
        result, raw = run_monte_carlo_batch(cenario, n_iterations=5000, seed=0)
        p_12m = probability_below(raw, threshold=12.0)
        assert 0.03 <= p_12m <= 0.12

    def test_lance_aumenta_probabilidade_precoce(self):
        """Com lance alto, contemplação precoce deve ser mais provável."""
        def sem_lance():
            for mes in range(1, 73):
                if random.random() < (1.0 / 200):
                    return float(mes)
            return 72.0

        def com_lance():
            for mes in range(1, 73):
                if random.random() < (1.0 / 200):
                    return float(mes)
                if random.random() < 0.30:
                    return float(mes)
            return 72.0

        _, raw_sem = run_monte_carlo_batch(sem_lance, n_iterations=3000, seed=10)
        _, raw_com = run_monte_carlo_batch(com_lance, n_iterations=3000, seed=10)

        assert probability_below(raw_com, 12.0) > probability_below(raw_sem, 12.0)
