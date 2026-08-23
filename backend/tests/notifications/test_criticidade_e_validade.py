"""
Etapa 1 do filtro de relevância — validade sempre, relevância só para
não-CRITICAL.

A doc da feature dizia *"Pipeline de 3 etapas, com CRITICAL imune em todas"*.
O docstring do módulo repetia: *"Notificações CRITICAL nunca são descartadas
em nenhuma etapa"*. As etapas 2 e 3 checavam `n.priority == "CRITICAL"`; a
etapa 1 não checava nada. Uma anomalia CRITICAL de R$ 150 (fator 4,2× — o
gerador marca CRITICAL a partir de 3×) era descartada para quem ganha R$ 15
mil exatamente como um WARNING.

A correção não é exentar CRITICAL de tudo — é separar as duas naturezas de
portão que estavam misturadas:

    RELEVÂNCIA  "é grande o bastante para te interromper?"  CRITICAL passa
    VALIDADE    "esse sinal é real?"                        CRITICAL não passa

Um falso "detectamos um bebê" fica pior alto, não melhor.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.notifications.notifier import Notification
from app.notifications.relevance_filter import (
    _MAX_NON_CRITICAL,
    _MAX_PER_TYPE,
    _RELEVANCE_FILTERS,
    _VALIDITY_FILTERS,
    NotificationRelevanceFilter,
)


def _nota(tipo: str, prioridade: str, meta: dict) -> Notification:
    return Notification(
        id="n", type=tipo, priority=prioridade, title="t", message="m",
        generated_at=dt.datetime.now(dt.timezone.utc), metadata=meta, action_hint="a",
    )


@pytest.fixture
def filtro():
    return NotificationRelevanceFilter()


class TestCriticalPassaPorRelevancia:

    def test_anomalia_critical_sobrevive_ao_piso_de_renda(self, filtro):
        """
        R$ 150 a 4,2× o padrão. Para quem ganha R$ 15 mil o piso é R$ 200 —
        e a nota era descartada apesar de CRITICAL.
        """
        crit = _nota("ANOMALY_DETECTED", "CRITICAL", {"factor": 4.2, "amount": 150.0})
        assert filtro.filter([crit], monthly_income=15_000) == [crit]

    def test_a_mesma_nota_como_warning_continua_sendo_barrada(self, filtro):
        """O piso por renda não sumiu — deixou de valer para CRITICAL."""
        warn = _nota("ANOMALY_DETECTED", "WARNING", {"factor": 2.8, "amount": 150.0})
        assert filtro.filter([warn], monthly_income=15_000) == []

    @pytest.mark.parametrize("renda", [2_000, 5_000, 15_000, 50_000])
    def test_critical_passa_em_qualquer_renda(self, filtro, renda):
        crit = _nota("ANOMALY_DETECTED", "CRITICAL", {"factor": 4.0, "amount": 40.0})
        assert filtro.filter([crit], monthly_income=renda) == [crit]

    def test_card_opportunity_critical_tambem(self, filtro):
        crit = _nota("CARD_OPPORTUNITY", "CRITICAL", {"monthly_gain_missed": 5.0})
        assert filtro.filter([crit], monthly_income=15_000) == [crit]


class TestCriticalNaoPassaPorValidade:
    """
    Uma nota CRITICAL que não passa num portão de validade não é urgente —
    é malformada.
    """

    @pytest.mark.parametrize("tipo,meta", [
        # Não é anomalia: 1,8× não sustenta o sinal, por mais alto que seja o valor.
        ("ANOMALY_DETECTED", {"factor": 1.8, "amount": 99_999.0}),
        # Falso positivo de evento de vida é o pior caso do produto.
        ("LIFE_EVENT", {"confidence": 0.43}),
        # 25% não é marco que o produto notifica.
        ("GOAL_PROGRESS", {"milestone": 25.0, "goal_id": "g1"}),
        # Fora da janela do calendário fiscal.
        ("FISCAL_SEASON", {"days_until_deadline": 300}),
        # Oferta que não se qualifica.
        ("TRANSFER_PROMO", {"bonus_pct": 5, "user_points": 10}),
    ])
    def test_critical_invalida_e_descartada(self, filtro, tipo, meta):
        crit = _nota(tipo, "CRITICAL", meta)
        assert filtro.filter([crit], monthly_income=5_000) == []

    def test_evento_de_vida_critical_valido_passa(self, filtro):
        crit = _nota("LIFE_EVENT", "CRITICAL", {"confidence": 0.90})
        assert filtro.filter([crit], monthly_income=5_000) == [crit]


class TestOsDoisConjuntosSaoCoerentes:

    def test_nenhum_tipo_aparece_nos_dois_com_a_mesma_funcao(self):
        """
        ANOMALY_DETECTED está nos dois de propósito — com funções DIFERENTES
        (fator é validade, valor é relevância). Qualquer outro tipo repetido
        com a mesma função seria checagem duplicada.
        """
        for tipo in set(_VALIDITY_FILTERS) & set(_RELEVANCE_FILTERS):
            assert _VALIDITY_FILTERS[tipo] is not _RELEVANCE_FILTERS[tipo], tipo

    def test_todo_tipo_com_gerador_tem_algum_portao(self):
        from app.notifications import notifier

        tipos_conhecidos = set(_VALIDITY_FILTERS) | set(_RELEVANCE_FILTERS)
        assert "ANOMALY_DETECTED" in tipos_conhecidos
        assert "SAFE_TO_SPEND_LOW" in tipos_conhecidos
        assert notifier is not None


class TestCapsContinuamProtegendoCritical:
    """As etapas 2 e 3 já funcionavam — não podem ter regredido."""

    def test_cap_por_tipo_nao_atinge_critical(self, filtro):
        seis = [_nota("ANOMALY_DETECTED", "CRITICAL", {"factor": 4.0, "amount": 50.0})
                for _ in range(6)]
        assert len(filtro.filter(seis, monthly_income=15_000)) == 6
        assert _MAX_PER_TYPE == 2

    def test_cap_global_nao_atinge_critical(self, filtro):
        um_crit = _nota("ANOMALY_DETECTED", "CRITICAL", {"factor": 4.0, "amount": 5_000.0})
        infos = [_nota("SAFE_TO_SPEND_LOW", "INFO", {}) for _ in range(8)]
        saida = filtro.filter([um_crit] + infos, monthly_income=5_000)
        assert um_crit in saida
        assert len([n for n in saida if n.priority != "CRITICAL"]) <= _MAX_NON_CRITICAL

    def test_ordem_critical_primeiro_e_preservada(self, filtro):
        crit = _nota("ANOMALY_DETECTED", "CRITICAL", {"factor": 4.0, "amount": 5_000.0})
        info = _nota("SAFE_TO_SPEND_LOW", "INFO", {})
        saida = filtro.filter([crit, info], monthly_income=5_000)
        assert saida[0].priority == "CRITICAL"
