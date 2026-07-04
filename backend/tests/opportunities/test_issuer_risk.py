# tests/opportunities/test_issuer_risk.py
"""V2 (docs/OPP.md §8.2) — tier de risco do emissor e bucket de liquidez."""

from app.opportunities.calculators.issuer_risk import (
    issuer_tier,
    liquidity_bucket,
    risk_penalty,
)


class TestIssuerTier:
    def test_bancao_e_tier_1(self):
        assert issuer_tier("Itaú") == 1
        assert issuer_tier("Caixa Econômica") == 1

    def test_digital_consolidado_e_tier_2(self):
        assert issuer_tier("Nubank") == 2
        assert issuer_tier("BTG Pactual") == 2

    def test_medio_pequeno_e_tier_3(self):
        assert issuer_tier("Sofisa Direto") == 3

    def test_desconhecido_e_conservador_tier_3(self):
        assert issuer_tier("Banco Inventado XYZ") == 3


class TestRiskPenalty:
    def test_penalidade_cresce_com_o_tier(self):
        assert risk_penalty(1) == 0.0
        assert risk_penalty(1) < risk_penalty(2) < risk_penalty(3)

    def test_tier_invalido_usa_penalidade_conservadora(self):
        assert risk_penalty(99) == risk_penalty(3)


class TestLiquidityBucket:
    def test_daily(self):
        assert liquidity_bucket(1, "daily") == "diaria"

    def test_ate_12m(self):
        assert liquidity_bucket(360, "12m") == "ate_12m"

    def test_longo_prazo(self):
        assert liquidity_bucket(720, "24m") == "longo_prazo"
