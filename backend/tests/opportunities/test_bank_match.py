# tests/opportunities/test_bank_match.py
"""
Bank Match — camada "melhor banco para o usuário": score composto
(rendimento + tarifas + cartões + fit) com pesos por perfil financeiro.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.opportunities.services.bank_match import BankMatchService
from app.opportunities.services.bank_scorecard import BankScorecardService


def _build(user_banks=None, user_profile=None, **kwargs):
    defaults = dict(
        user_id="user_test",
        amount=10_000.0,
        holding_months=12,
        cdi_annual=0.1465,
        selic_annual=0.15,
        user_profile=user_profile,
    )
    defaults.update(kwargs)
    with patch.object(BankScorecardService, "_get_user_banks", return_value=user_banks or set()):
        return BankMatchService().build(**defaults)


class TestRankingComposto:
    def test_ranking_ordenado_por_match_score(self):
        result = _build()
        scores = [e.match_score for e in result.ranking]
        assert scores == sorted(scores, reverse=True)
        assert result.best_bank == result.ranking[0].bank_name

    def test_componentes_entre_0_e_100(self):
        result = _build()
        for e in result.ranking:
            for v in (e.components.yield_score, e.components.fees_score,
                      e.components.card_score, e.components.fit_score, e.match_score):
                assert 0.0 <= v <= 100.0

    def test_cartao_do_banco_correto_nao_vaza_entre_emissores(self):
        """Regressão: token genérico 'bank' casava Nubank com C6 Bank."""
        result = _build()
        by_name = {e.bank_name: e for e in result.ranking}
        c6 = by_name.get("C6 Bank")
        if c6 is not None and c6.top_card_name:
            assert "nubank" not in c6.top_card_name.lower()

    def test_reasons_explicam_o_score(self):
        result = _build()
        assert all(e.reasons for e in result.ranking)


class TestPesosPorPerfil:
    def test_perfil_fragil_prioriza_tarifas_e_fit(self):
        fragile = SimpleNamespace(fss_level="CRITICO", investor_type="NONE",
                                  lifestyle_cluster="NAO_CLASSIFICADO")
        result = _build(user_profile=fragile)
        w = result.profile_used["weights"]
        assert w["fees"] > w["yield"]
        assert result.profile_used["fss_level"] == "CRITICO"

    def test_investidor_ativo_prioriza_rendimento(self):
        investor = SimpleNamespace(fss_level="SAUDAVEL", investor_type="ATIVO",
                                   lifestyle_cluster="NAO_CLASSIFICADO")
        result = _build(user_profile=investor)
        w = result.profile_used["weights"]
        assert w["yield"] == max(w.values())

    def test_sem_perfil_usa_pesos_padrao(self):
        result = _build(user_profile=None)
        w = result.profile_used["weights"]
        assert w == {"yield": 0.40, "fees": 0.30, "card": 0.15, "fit": 0.15}
        assert sum(w.values()) == pytest.approx(1.0)


class TestBancoAtualERecomendacao:
    def test_banco_atual_marcado_e_ranqueado(self):
        result = _build(user_banks={"Nubank"})
        assert result.user_current_bank == "Nubank"
        assert result.user_current_bank_rank >= 1

    def test_atual_ja_e_o_melhor_nao_recomenda_troca(self):
        result = _build(user_banks={"Nubank"})
        if result.best_bank == "Nubank":
            assert "não há troca" in result.switch_recommendation

    def test_diferenca_pequena_nao_recomenda_troca(self):
        """Gap de score < 5 pontos → não sugerir migração."""
        result = _build(user_banks={"Banco Inter"})
        best = result.ranking[0]
        current = next(e for e in result.ranking if e.is_user_current_bank)
        if best.bank_name != current.bank_name and best.match_score - current.match_score < 5.0:
            assert "não justifica" in result.switch_recommendation

    def test_sem_banco_conectado_sugere_conectar(self):
        result = _build(user_banks=set())
        assert result.user_current_bank is None
        assert "Conecte" in result.switch_recommendation


class TestDegradacaoGraciosa:
    def test_tarifas_indisponiveis_usa_nota_neutra(self):
        with patch(
            "app.costs.market_fees_db.MarketFeesDB.get_avg_for_bank",
            side_effect=Exception("db fora"),
        ):
            result = _build()
        assert result.ranking  # análise não cai
        assert all(e.components.fees_score == 50.0 for e in result.ranking)

    def test_cartoes_indisponiveis_usa_nota_neutra(self):
        with patch(
            "app.optimizer.card_loader.CardKnowledgeBase.load",
            side_effect=Exception("catálogo fora"),
        ):
            result = _build()
        assert result.ranking
        assert all(e.components.card_score == 50.0 for e in result.ranking)
        assert all(e.top_card_name is None for e in result.ranking)
