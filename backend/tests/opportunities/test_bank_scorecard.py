# tests/opportunities/test_bank_scorecard.py
"""V2 (docs/OPP.md §8.2) — BankScorecardService: ranking agregado por banco,
ajuste a risco por tier do emissor e cruzamento com o banco atual (Pluggy)."""

from unittest.mock import patch

import pytest

from app.opportunities.services.bank_scorecard import BankScorecardService


def _build(user_banks: set[str] | None = None, **kwargs):
    service = BankScorecardService()
    defaults = dict(
        user_id="user_test",
        amount=10_000.0,
        holding_months=12,
        cdi_annual=0.1465,
        selic_annual=0.15,
    )
    defaults.update(kwargs)
    with patch.object(
        BankScorecardService, "_get_user_banks", return_value=user_banks or set()
    ):
        return service.build(**defaults)


class TestScorecard:
    def test_uma_entrada_por_banco_ordenada_por_risco_ajustado(self):
        result = _build()
        names = [e.bank_name for e in result.scorecard]
        assert len(names) == len(set(names))  # sem banco duplicado
        adjusted = [e.best_risk_adjusted_brl for e in result.scorecard]
        assert adjusted == sorted(adjusted, reverse=True)

    def test_tier_1_nao_tem_penalidade(self):
        result = _build()
        for entry in result.scorecard:
            if entry.risk_tier == 1:
                assert entry.best_risk_adjusted_brl == pytest.approx(
                    entry.best_net_return_brl, abs=0.01
                )
            else:
                assert entry.best_risk_adjusted_brl < entry.best_net_return_brl

    def test_best_by_liquidity_tem_bucket_diaria(self):
        result = _build()
        assert "diaria" in result.best_by_liquidity

    def test_tesouro_direto_e_tier_1(self):
        result = _build()
        tesouro = next((e for e in result.scorecard if e.bank_name == "Tesouro Direto"), None)
        assert tesouro is not None
        assert tesouro.risk_tier == 1
        assert tesouro.fgc_covered is False


class TestBancoAtualDoUsuario:
    def test_sem_bancos_conectados_nao_marca_ninguem(self):
        result = _build()
        assert result.user_current_bank is None
        assert result.user_current_bank_rank is None

    def test_banco_conectado_e_marcado_e_ranqueado(self):
        result = _build(user_banks={"Nubank"})
        assert result.user_current_bank == "Nubank"
        assert result.user_current_bank_rank >= 1
        entry = next(e for e in result.scorecard if e.bank_name == "Nubank")
        assert entry.is_user_current_bank is True

    def test_match_tolerante_de_connector_name(self):
        """connector_name do Pluggy raramente é idêntico ao bank_name."""
        result = _build(user_banks={"Nu Pagamentos S.A."})
        assert result.user_current_bank == "Nubank"

    def test_switch_gain_e_diferenca_para_o_melhor(self):
        result = _build(user_banks={"Nubank"})
        best = result.scorecard[0]
        if best.bank_name != "Nubank":
            nubank = next(e for e in result.scorecard if e.bank_name == "Nubank")
            assert result.switch_gain_brl == pytest.approx(
                best.best_net_return_brl - nubank.best_net_return_brl, abs=0.01
            )

    def test_disclaimer_presente(self):
        result = _build(disclaimer="teste de disclaimer")
        assert result.disclaimer == "teste de disclaimer"
