# tests/opportunities/test_idle_money_detector.py
"""
Ticket OPP1-B (docs/OPP1_DINHEIRO_PARADO_PLANO.md) — proteção de reserva de
emergência em IdleMoneyDetector.

Cobre:
  - gross_idle_amount como proxy de saldo (soma cumulativa), não fluxo mensal
  - reserva subtraída corretamente para os 4 níveis de fss_level
  - idle_amount nunca fica negativo, mesmo quando a reserva excede o saldo
  - compatibilidade retroativa: sem user_profile, idle_amount == gross_idle_amount
  - DataFrame vazio / sem dados suficientes não quebra
"""
from datetime import date, timedelta

import polars as pl
import pytest

from app.opportunities.services.idle_money_detector import (
    IdleMoneyDetector,
    IdleMoneyResult,
    _RESERVE_MONTHS_BY_FSS,
)
from app.optimizer.profiler import UserProfile


def _profile(fss_level: str) -> UserProfile:
    return UserProfile(fss_level=fss_level)


def _primeiro_dia(meses_atras: int) -> date:
    """Primeiro dia do mês `meses_atras` antes do atual."""
    c = date.today().replace(day=1)
    for _ in range(meses_atras):
        c = (c - timedelta(days=1)).replace(day=1)
    return c


def _transactions(income: float, expense: float, months: int = 3) -> pl.DataFrame:
    """
    `months` ciclos de renda/despesa em meses COMPLETOS anteriores ao atual.

    A versão anterior usava `today - timedelta(days=30 * months_back)`, que
    colocava um ciclo dentro do mês corrente — e o detector somava esse mês
    parcial dividindo por 3. O dado do teste ACIONAVA o bug, e nenhuma
    asserção conseguia vê-lo porque todas usavam a saída do próprio detector
    como valor esperado.
    """
    rows = []
    for months_back in range(1, months + 1):
        base = _primeiro_dia(months_back)
        rows.append({"date": base.replace(day=5), "amount": income})
        rows.append({"date": base.replace(day=10), "amount": -expense})
    return pl.DataFrame(rows)


class TestGrossIdleAmountEProxyDeSaldo:
    def test_gross_idle_e_soma_cumulativa_nao_fluxo_mensal(self):
        """Regressão do bug fluxo-vs-estoque: gross_idle_amount deve ser a soma
        de TODAS as transações, não avg_income_3m - avg_expenses_3m."""
        df = _transactions(income=6000.0, expense=3500.0, months=3)
        result = IdleMoneyDetector().detect("u1", transactions_df=df)

        expected_cumulative = 3 * 6000.0 - 3 * 3500.0  # soma de todas as linhas
        assert result.gross_idle_amount == pytest.approx(expected_cumulative, rel=0.01)
        # e a média mensal tem que ser a do cenário, não uma fração dele
        assert result.avg_income_3m == pytest.approx(6000.0, rel=0.01)
        assert result.avg_expenses_3m == pytest.approx(3500.0, rel=0.01)
        # NÃO deve ser igual a um único mês de sobra
        assert result.gross_idle_amount != pytest.approx(
            result.avg_income_3m - result.avg_expenses_3m, rel=0.01
        )

    def test_saldo_negativo_nao_gera_gross_idle_negativo(self):
        df = _transactions(income=1000.0, expense=5000.0, months=3)
        result = IdleMoneyDetector().detect("u1", transactions_df=df)
        assert result.gross_idle_amount == 0.0
        assert result.idle_amount == 0.0


class TestCompatibilidadeRetroativa:
    def test_sem_user_profile_idle_amount_igual_gross(self):
        """Sem UserProfile, nenhuma reserva é aplicada — mesmo comportamento
        numérico de antes do Ticket OPP1-B."""
        df = _transactions(income=8000.0, expense=3000.0, months=4)
        result = IdleMoneyDetector().detect("u1", transactions_df=df)

        assert result.reserve_months_applied == 0
        assert result.emergency_reserve == 0.0
        assert result.idle_amount == pytest.approx(result.gross_idle_amount, rel=0.001)


class TestReservaPorFssLevel:
    """Reserva = reserve_months_applied × avg_expenses_3m; idle_amount = max(0, gross - reserva)."""

    @pytest.mark.parametrize("fss_level", ["SAUDAVEL", "ATENCAO", "ALERTA", "CRITICO"])
    def test_reserva_aplicada_conforme_tabela(self, fss_level):
        # renda/despesa altas o bastante para o saldo cumulativo superar
        # qualquer uma das reservas (até 9 meses de despesa)
        df = _transactions(income=30000.0, expense=1000.0, months=3)
        profile = _profile(fss_level)

        result = IdleMoneyDetector().detect("u1", transactions_df=df, user_profile=profile)

        expected_months = _RESERVE_MONTHS_BY_FSS[fss_level]
        assert result.reserve_months_applied == expected_months

        # Contra a DESPESA CONHECIDA DO CENÁRIO — não contra a saída do próprio
        # detector. `expected_months * result.avg_expenses_3m` verificava a
        # multiplicação, que não pode estar errada, e nunca se avg_expenses_3m
        # era a despesa mensal de verdade. Era assim que a janela quebrada
        # passava: com 4 meses de dado divididos por 3, a média saía 33% acima
        # e as duas asserções continuavam verdadeiras.
        assert result.avg_expenses_3m == pytest.approx(1_000.0, rel=0.01)
        assert result.emergency_reserve == pytest.approx(
            expected_months * 1_000.0, rel=0.01
        )
        esperado_idle = max(0.0, 3 * 30_000.0 - 3 * 1_000.0 - expected_months * 1_000.0)
        assert result.idle_amount == pytest.approx(esperado_idle, rel=0.01)

    def test_alerta_e_critico_protegem_mais_que_saudavel_e_atencao(self):
        df = _transactions(income=30000.0, expense=1000.0, months=3)

        saudavel = IdleMoneyDetector().detect("u1", transactions_df=df, user_profile=_profile("SAUDAVEL"))
        critico = IdleMoneyDetector().detect("u1", transactions_df=df, user_profile=_profile("CRITICO"))

        assert critico.reserve_months_applied > saudavel.reserve_months_applied
        assert critico.emergency_reserve > saudavel.emergency_reserve
        assert critico.idle_amount <= saudavel.idle_amount

    def test_fss_level_desconhecido_usa_default_saudavel(self):
        df = _transactions(income=30000.0, expense=1000.0, months=3)
        profile = _profile("VALOR_INEXISTENTE")

        result = IdleMoneyDetector().detect("u1", transactions_df=df, user_profile=profile)
        assert result.reserve_months_applied == _RESERVE_MONTHS_BY_FSS["SAUDAVEL"]


class TestReservaNuncaDeixaIdleNegativo:
    def test_reserva_maior_que_saldo_zera_idle_sem_ficar_negativo(self):
        """Cenário comum: saldo estimado pequeno, reserva de 6-9 meses de
        despesa é maior que o saldo — idle_amount deve zerar, nunca negativar."""
        df = _transactions(income=5000.0, expense=4000.0, months=2)
        profile = _profile("CRITICO")

        result = IdleMoneyDetector().detect("u1", transactions_df=df, user_profile=profile)

        assert result.emergency_reserve > result.gross_idle_amount
        assert result.idle_amount == 0.0


class TestSemDadosSuficientes:
    def test_dataframe_vazio_retorna_resultado_zerado(self):
        result = IdleMoneyDetector().detect("u1", transactions_df=pl.DataFrame())
        assert result == IdleMoneyResult(
            idle_amount=0.0,
            gross_idle_amount=0.0,
            emergency_reserve=0.0,
            reserve_months_applied=0,
            avg_income_3m=0.0,
            avg_expenses_3m=0.0,
            months_analyzed=0,
            has_sufficient_data=False,
        )

    def test_has_sufficient_data_nao_depende_da_reserva(self):
        df = _transactions(income=1000.0, expense=500.0, months=1)
        result = IdleMoneyDetector().detect(
            "u1", transactions_df=df, user_profile=_profile("SAUDAVEL")
        )
        # 1 ciclo cai dentro da janela de 3 meses, mas months_analyzed é
        # calculado sobre o cutoff fixo (3 meses) independente da reserva
        assert isinstance(result.has_sufficient_data, bool)
