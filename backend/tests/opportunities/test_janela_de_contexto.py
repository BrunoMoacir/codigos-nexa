"""
OPP.1 — a janela que dimensiona a reserva de emergência.

Quatro linhas de código produziam erro em DUAS direções, conforme o formato do
histórico do usuário:

    cutoff = today.replace(day=1)
    for _ in range(3):
        cutoff = (cutoff - timedelta(days=1)).replace(day=1)
    df_recent = df.filter(pl.col(date_col) >= cutoff)      # sem limite superior
    months = max(1, (today.year - cutoff.year) * 12 + today.month - cutoff.month)

O filtro pegava o mês corrente (pela metade) e o divisor era a LARGURA da
janela — sempre 3, porque o cutoff é sempre 3 meses atrás. Com gasto real de
R$ 4.800/mês e reserva de 6 meses (R$ 28.800 correto):

    3 completos + mês corrente  → reserva R$ 38.400  (+33%, e crescendo ao
                                  longo do mês: dia 1 ≠ dia 28)
    1 mês de histórico          → reserva R$  9.600  (um TERÇO — o lado
                                  perigoso: sugere investir a reserva)
    só histórico antigo         → reserva R$ 115.200 (o fallback somava 12
                                  meses e dividia por 3)

E como `months` era constante em 3, `has_sufficient_data = months >= 2` era
sempre True: o status NO_DATA do engine era inalcançável em produção.

Os 181 testes que existiam passavam nos dois estados porque as asserções sobre
a reserva usavam a saída do próprio detector como valor esperado
(`expected_months * result.avg_expenses_3m`). Verificavam a multiplicação, que
não pode estar errada. Aqui todo valor esperado vem do CENÁRIO.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from app.opportunities.services.idle_money_detector import IdleMoneyDetector
from app.optimizer.profiler import UserProfile

_RENDA = 9_000.0
_GASTO = 4_800.0
_RESERVA_SAUDAVEL = 6 * _GASTO      # R$ 28.800 — o número correto em todo caso


def _primeiro_dia(meses_atras: int) -> dt.date:
    c = dt.date.today().replace(day=1)
    for _ in range(meses_atras):
        c = (c - dt.timedelta(days=1)).replace(day=1)
    return c


def _ciclo(quando: dt.date, renda=_RENDA, gasto=_GASTO) -> list[dict]:
    return [
        {"date": quando.replace(day=5), "amount": renda, "description": "SALARIO"},
        {"date": quando.replace(day=10), "amount": -gasto, "description": "GASTOS"},
    ]


def _detectar(linhas: list[dict], fss: str = "SAUDAVEL"):
    return IdleMoneyDetector().detect(
        "u",
        transactions_df=pl.DataFrame(linhas),
        user_profile=UserProfile(fss_level=fss),
    )


class TestAMediaEDeVerdadeMediaMensal:
    """
    Toda asserção compara contra R$ 4.800 — o gasto que o cenário construiu.
    """

    def test_tres_meses_completos(self):
        r = _detectar([x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))])
        assert r.avg_expenses_3m == pytest.approx(_GASTO, rel=0.01)
        assert r.emergency_reserve == pytest.approx(_RESERVA_SAUDAVEL, rel=0.01)

    def test_mes_corrente_PARCIAL_nao_entra_na_media(self):
        """
        O mês corrente está pela metade — algumas despesas já caíram, outras
        não. É o caso REAL de produção, e o único que exercita o limite
        superior do filtro sozinho.

        Um ciclo completo dentro do mês corrente não serve de teste: 4 meses
        divididos por 4 dão a média certa por acaso, e a mutação que remove o
        limite superior passa despercebida (foi o que aconteceu na primeira
        rodada). Com o mês pela metade, contá-lo como mês inteiro DILUI a
        média: R$ 4.800 vira R$ 3.600 e a reserva cai de R$ 28.800 para
        R$ 21.600 — R$ 7.200 a menos protegidos, o lado perigoso.
        """
        so_completos = [x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))]
        # só a renda do mês corrente entrou; a despesa do fim do mês, não
        com_parcial = so_completos + [
            {"date": dt.date.today().replace(day=1), "amount": _RENDA,
             "description": "SALARIO"}
        ]

        r = _detectar(com_parcial)
        assert r.months_analyzed == 3, "o mês corrente entrou na contagem"
        assert r.avg_expenses_3m == pytest.approx(_GASTO, rel=0.01)
        assert r.emergency_reserve == pytest.approx(_RESERVA_SAUDAVEL, rel=0.01)

    def test_mes_corrente_completo_tambem_fica_fora(self):
        so_completos = [x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))]
        com_corrente = so_completos + _ciclo(dt.date.today().replace(day=1))

        assert _detectar(so_completos).emergency_reserve == pytest.approx(
            _detectar(com_corrente).emergency_reserve, rel=0.01
        )

    @pytest.mark.parametrize("meses", [1, 2, 3])
    def test_historico_curto_nao_encolhe_a_media(self, meses):
        """
        O lado PERIGOSO do defeito. Com 1 mês de dado o divisor continuava 3,
        a média virava um terço da real e a reserva protegida caía de
        R$ 28.800 para R$ 9.600 — o motor passaria a sugerir investir dinheiro
        que é reserva de emergência.
        """
        r = _detectar([x for i in range(1, meses + 1) for x in _ciclo(_primeiro_dia(i))])
        assert r.avg_expenses_3m == pytest.approx(_GASTO, rel=0.01)
        assert r.emergency_reserve == pytest.approx(_RESERVA_SAUDAVEL, rel=0.01)
        assert r.months_analyzed == meses

    def test_historico_antigo_nao_infla_a_media(self):
        """
        Quando nada cai na janela o detector usa todo o histórico — mas o
        divisor tem que sair do dado, não da largura da janela. Somar 12 meses
        e dividir por 3 levava a reserva a R$ 115.200.
        """
        antigo = [x for m in range(1, 13) for x in _ciclo(dt.date(2025, m, 1))]
        r = _detectar(antigo)
        assert r.avg_expenses_3m == pytest.approx(_GASTO, rel=0.01)
        assert r.months_analyzed == 12

    def test_renda_tambem(self):
        r = _detectar([x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))])
        assert r.avg_income_3m == pytest.approx(_RENDA, rel=0.01)


class TestSuficienciaDeHistorico:
    """
    `has_sufficient_data` era sempre True porque `months` era constante em 3.
    O status NO_DATA do engine — a proteção contra recomendar sobre nada —
    nunca era alcançado.
    """

    def test_um_mes_e_insuficiente(self):
        assert _detectar(_ciclo(_primeiro_dia(1))).has_sufficient_data is False

    @pytest.mark.parametrize("meses", [2, 3])
    def test_dois_meses_ja_bastam(self, meses):
        r = _detectar([x for i in range(1, meses + 1) for x in _ciclo(_primeiro_dia(i))])
        assert r.has_sufficient_data is True

    def test_historico_antigo_nao_sustenta_recomendacao_de_hoje(self):
        """
        Volume não substitui atualidade: 12 meses de 2025 descrevem uma vida
        financeira que pode não existir mais, e o saldo proxy é igualmente
        velho.
        """
        r = _detectar([x for m in range(1, 13) for x in _ciclo(dt.date(2025, m, 1))])
        assert r.historico_desatualizado is True
        assert r.has_sufficient_data is False


class TestOEngineReflecteIsso:

    def _analisar(self, linhas):
        from unittest.mock import patch

        from app.opportunities.services.opportunity_engine import OpportunityEngine

        with patch.object(
            OpportunityEngine, "_fetch_transactions", return_value=pl.DataFrame(linhas)
        ):
            return OpportunityEngine().analyze("u", persist_snapshot=False)

    def test_historico_curto_vira_NO_DATA(self):
        r = self._analisar(_ciclo(_primeiro_dia(1)))
        assert r.idle_detection_status == "NO_DATA"
        assert "insuficiente" in r.idle_detection_reason

    def test_historico_antigo_vira_NO_DATA_com_motivo_proprio(self):
        r = self._analisar([x for m in range(1, 13) for x in _ciclo(dt.date(2025, m, 1))])
        assert r.idle_detection_status == "NO_DATA"
        assert "antigo" in r.idle_detection_reason

    def test_historico_bom_nao_vira_NO_DATA(self):
        r = self._analisar([x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))])
        assert r.idle_detection_status != "NO_DATA"
        assert r.avg_expenses_3m == pytest.approx(_GASTO, rel=0.01)


class TestReservaCresceComAFragilidade:
    """
    A semântica documentada: quem está em ALERTA/CRÍTICO tem MAIS dinheiro
    blindado contra a sugestão de investir, não menos. Com a média correta, o
    número absoluto passa a ser verificável.
    """

    @pytest.mark.parametrize(
        "fss,meses_esperados",
        [("SAUDAVEL", 6), ("ATENCAO", 6), ("ALERTA", 9), ("CRITICO", 9)],
    )
    def test_reserva_por_nivel(self, fss, meses_esperados):
        linhas = [x for i in (1, 2, 3) for x in _ciclo(_primeiro_dia(i))]
        r = _detectar(linhas, fss=fss)

        assert r.reserve_months_applied == meses_esperados
        assert r.emergency_reserve == pytest.approx(meses_esperados * _GASTO, rel=0.01)
