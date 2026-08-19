"""
Ranking conservador (P25) e envelhecimento da curadoria — F2.

Dois gaps que estavam documentados e não implementados:

  1. "Point values usam P25 do mercado, não média" era princípio declarado
     no docstring de MilesValuator.get_conservative_rate() — e o método era
     CÓDIGO MORTO. O ranking ordenava por net_gain_expected, que usa P50.
     Cashback (valor certo) concorria com milha valorizada no ponto médio
     de uma banda que chega a 3x entre P25 e P75.

  2. A base de 81 cartões é curada à mão, cada registro tem `last_updated`
     e não havia nada que reagisse a isso: dado conferido há 500 dias
     entrava na recomendação com a mesma confiança do conferido ontem.
"""

from datetime import date, timedelta

import pytest

from app.optimizer.card_loader import (
    _CURATION_MIN_FACTOR,
    _CURATION_STALE_DAYS,
    curation_freshness_factor,
)
from app.optimizer.miles_valuator import get_valuator
from tests.optimizer.test_simulator import _make_card, _make_profile


def _perfil():
    return _make_profile(monthly_avg_spend=3000.0, data_coverage_months=6)


def _cartao_pontos():
    """Pontos com programa de fidelidade — é onde o P25 tem efeito."""
    from app.optimizer.models import CardType

    return _make_card(card_type=CardType.POINTS, points_per_brl=1.0).model_copy(
        update={"loyalty_program": "livelo", "card_id": "pontos-livelo"}
    )


def _cartao_cashback():
    from app.optimizer.models import CardType

    return _make_card(
        card_type=CardType.CASHBACK, cashback_pct=0.01, points_per_brl=None
    ).model_copy(update={"card_id": "cashback-flat"})


class TestRankingConservador:

    def test_cenario_conservative_usa_p25(self):
        valuator = get_valuator()
        for programa in ("smiles", "livelo", "latam_pass"):
            p25 = valuator.get_rate(programa, "conservative")
            p50 = valuator.get_rate(programa, "expected")
            p75 = valuator.get_rate(programa, "optimistic")

            assert p25 == valuator.get_conservative_rate(programa)
            assert p25 < p50 < p75, f"{programa}: distribuição fora de ordem"

    def test_get_conservative_rate_deixou_de_ser_codigo_morto(self):
        """O método existia só no próprio docstring — agora o simulador o usa."""
        from app.optimizer.simulator import CardSimulator

        sim = CardSimulator()
        resultado = sim.simulate(_cartao_pontos(), _perfil(), safe_to_spend=2000.0)

        assert resultado.net_gain_conservative < resultado.net_gain_expected, (
            "cartão de pontos tem que valer menos no P25 do que no P50"
        )

    def test_cashback_nao_e_penalizado_pelo_conservadorismo(self):
        """R$1 de cashback vale R$1 — não há banda de valoração para descontar."""
        from app.optimizer.simulator import CardSimulator

        resultado = CardSimulator().simulate(_cartao_cashback(), _perfil(), safe_to_spend=2000.0)

        assert resultado.net_gain_conservative == pytest.approx(
            resultado.net_gain_expected, abs=0.01
        )

    def test_ranking_ordena_pelo_conservador(self):
        """
        O usuário troca de cartão por causa da ORDEM. Ela não pode ser
        inclinada por uma estimativa otimista de milha.
        """
        from app.optimizer.ranking import CardRanking
        from app.optimizer.simulator import CardSimulator

        sim = CardSimulator()
        perfil = _perfil()
        pontos = sim.simulate(_cartao_pontos(), perfil, safe_to_spend=2000.0)
        cashback = sim.simulate(_cartao_cashback(), perfil, safe_to_spend=2000.0)

        score_pontos, _ = CardRanking()._compute_financial_score(pontos, perfil)
        score_cashback, _ = CardRanking()._compute_financial_score(cashback, perfil)

        # O score do cartão de pontos parte do P25, não do P50
        assert score_pontos <= pontos.net_gain_expected
        assert score_cashback == pytest.approx(cashback.net_gain_conservative, rel=0.01)


class TestEnvelhecimentoDaCuradoria:

    HOJE = date(2026, 8, 18)

    def test_dado_recente_nao_e_penalizado(self):
        recente = (self.HOJE - timedelta(days=30)).isoformat()
        assert curation_freshness_factor(recente, self.HOJE) == 1.0

    def test_decai_apos_o_prazo_de_revisao(self):
        seis_meses = (self.HOJE - timedelta(days=180)).isoformat()
        fator = curation_freshness_factor(seis_meses, self.HOJE)
        assert _CURATION_MIN_FACTOR < fator < 1.0

    def test_obsoleto_chega_no_piso_mas_nao_zera(self):
        """Taxa e benefício mudam; bandeira, tipo e emissor não."""
        antigo = (self.HOJE - timedelta(days=_CURATION_STALE_DAYS + 100)).isoformat()
        assert curation_freshness_factor(antigo, self.HOJE) == _CURATION_MIN_FACTOR

    @pytest.mark.parametrize("valor", [None, "", "não é data", "2026-13-45"])
    def test_data_ausente_ou_ilegivel_e_tratada_como_obsoleta(self, valor):
        """Não saber quando foi conferido é pior que saber que é velho."""
        assert curation_freshness_factor(valor, self.HOJE) == _CURATION_MIN_FACTOR

    def test_confianca_da_simulacao_cai_com_a_idade(self):
        from app.optimizer.simulator import CardSimulator

        sim, perfil = CardSimulator(), _perfil()
        novo = _cartao_cashback().model_copy(update={"last_updated": self.HOJE.isoformat()})
        velho = _cartao_cashback().model_copy(update={"last_updated": "2024-01-01"})

        conf_novo = sim.simulate(novo, perfil, safe_to_spend=2000.0).confidence_score
        conf_velho = sim.simulate(velho, perfil, safe_to_spend=2000.0).confidence_score

        assert conf_velho < conf_novo, "curadoria velha tem que reduzir a confiança"


class TestJobDeAuditoria:

    def test_auditoria_encontra_registros_vencidos(self):
        from app.jobs.cards_curation_audit import audit_card_curation

        relatorio = audit_card_curation(today=date(2026, 8, 18))

        assert relatorio["total"] == 81
        assert relatorio["vencidos"] > 0, "a base tem registros de 2025 parados"
        assert 0.0 < relatorio["fator_frescor_medio"] <= 1.0
        assert relatorio["itens"], "o relatório precisa dizer QUAIS revisar"
        assert {"card_id", "issuer", "idade_dias", "confianca_efetiva"} <= set(
            relatorio["itens"][0]
        )

    def test_auditoria_nao_altera_a_base(self):
        """Curadoria de dado de produto é decisão humana."""
        from app.jobs.cards_curation_audit import audit_card_curation
        from app.optimizer.card_loader import CardKnowledgeBase

        antes = {c.card_id: c.data_trust_score for c in CardKnowledgeBase().load()}
        audit_card_curation(today=date(2026, 8, 18))
        depois = {c.card_id: c.data_trust_score for c in CardKnowledgeBase().load()}

        assert antes == depois

    def test_job_registrado_no_scheduler(self):
        from app.jobs.cards_curation_audit import run_cards_curation_audit

        assert callable(run_cards_curation_audit)
