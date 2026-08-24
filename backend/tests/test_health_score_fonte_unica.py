"""
Health score: uma régua só.

A doc admitia DOIS scores (`financial_health_score` de 3 fatores e
`resilience_score` de 6). Havia um TERCEIRO, calculado inline em
`app/forecast/router.py`:

    savings_score  = min(70.0, savings_rate * 5.0 * 70.0)
    spending_score = (1.0 - income_ratio) * 30.0
    health_score   = min(100, max(0, round(savings_score + spending_score)))

Divergência de até 47 pontos contra o oficial — poupança de 2% valia 55 pela
régua de 3 fatores e 8 por esta.

O pior não era existir: era QUANDO entrava. O inline era calculado e depois
SOBRESCRITO sempre que o `UserProfileAnalyzer` funcionava. Ele só chegava ao
usuário quando `analyze()` levantava exceção — engolida num `logger.debug`.
Um erro silencioso mudava o score em meia escala, sem sinal nenhum.

E o `profile_type` NUNCA era sobrescrito: o payload saía com score de uma
régua e rótulo de outra.
"""

from __future__ import annotations

import pytest

from app.forecast.etl.profiles import UserProfileAnalyzer
from app.forecast.router import _perfil_e_score


class _PerfilFake:
    def __init__(self, tipo: str, score: int):
        self.profile_type = tipo
        self.financial_health_score = score


class TestFonteUnica:

    def test_com_o_analyzer_usa_o_resultado_dele(self):
        tipo, score = _perfil_e_score(
            _PerfilFake("CONSERVADOR", 90),
            savings_rate_pct=25.0, income=5_000.0, expenses=3_750.0,
        )
        assert (tipo, score) == ("CONSERVADOR", 90)

    @pytest.mark.parametrize("poupanca", [0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.50])
    def test_sem_o_analyzer_usa_a_MESMA_regua(self, poupanca):
        """
        O fallback aplica os mesmos métodos do analyzer sobre o que sobrou —
        não uma segunda fórmula. É a diferença entre um fallback com menos
        informação e um fallback com outra régua.
        """
        renda = 5_000.0
        despesa = renda * (1 - poupanca)
        tipo, score = _perfil_e_score(
            None, savings_rate_pct=poupanca * 100, income=renda, expenses=despesa,
        )
        analyzer = UserProfileAnalyzer()
        assert score == analyzer._calculate_health_score(poupanca * 100, despesa, renda)
        assert tipo == analyzer._determine_profile_type(poupanca * 100)

    @pytest.mark.parametrize("poupanca,minimo", [(0.02, 50), (0.10, 70), (0.25, 85)])
    def test_a_formula_removida_dava_muito_menos(self, poupanca, minimo):
        """
        Trava a diferença que motivou a correção: a fórmula inline produzia
        8 onde a oficial produz 55.
        """
        renda = 5_000.0
        despesa = renda * (1 - poupanca)
        _tipo, score = _perfil_e_score(
            None, savings_rate_pct=poupanca * 100, income=renda, expenses=despesa,
        )
        income_ratio = min(despesa / renda, 1.0)
        formula_removida = min(100, max(0, round(
            min(70.0, poupanca * 5.0 * 70.0) + (1.0 - income_ratio) * 30.0
        )))
        assert score >= minimo
        assert score > formula_removida


class TestVocabularioDeRotulo:
    """
    O router classificava com outra régua: POUPADOR acima de 40%,
    EQUILIBRADO a partir de 5%. Uma poupança de 22% saía "EQUILIBRADO" com
    score de "CONSERVADOR", no mesmo payload.
    """

    @pytest.mark.parametrize("poupanca,esperado", [
        (0.02, "GASTADOR"),
        (0.06, "GASTADOR"),        # a régua antiga dizia EQUILIBRADO
        (0.12, "EQUILIBRADO"),
        (0.22, "CONSERVADOR"),     # a régua antiga dizia EQUILIBRADO
        (0.45, "CONSERVADOR"),     # a régua antiga dizia POUPADOR
    ])
    def test_o_rotulo_segue_a_regua_do_analyzer(self, poupanca, esperado):
        tipo, _score = _perfil_e_score(
            None, savings_rate_pct=poupanca * 100,
            income=5_000.0, expenses=5_000.0 * (1 - poupanca),
        )
        assert tipo == esperado

    def test_POUPADOR_nao_e_mais_produzido(self):
        """
        Não existe no vocabulário do analyzer
        (`CONSERVADOR | EQUILIBRADO | GASTADOR`) — só a régua removida o
        emitia.
        """
        for poupanca in (0.30, 0.45, 0.60, 0.90):
            tipo, _ = _perfil_e_score(
                None, savings_rate_pct=poupanca * 100,
                income=5_000.0, expenses=5_000.0 * (1 - poupanca),
            )
            assert tipo != "POUPADOR"

    def test_o_analyzer_e_o_router_concordam_em_toda_a_faixa(self):
        analyzer = UserProfileAnalyzer()
        for pct in range(0, 100, 3):
            tipo, _ = _perfil_e_score(
                None, savings_rate_pct=float(pct),
                income=5_000.0, expenses=5_000.0 * (1 - pct / 100),
            )
            assert tipo == analyzer._determine_profile_type(float(pct)), pct
