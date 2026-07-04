# tests/opportunities/test_savings_rate.py
"""
Ticket OPP4-B (docs/OPP4_POUPANCA_CDI_PLANO.md) — fórmula oficial da poupança.

Fixtures obrigatórias da seção 5.6 do plano: selic_high_tr_zero,
selic_high_tr_positive, selic_low_boundary, selic_low_tr_zero.
"""
import pytest

from app.opportunities.services.savings_rate import (
    calculate_savings_rate,
    _SELIC_THRESHOLD_ANNUAL,
    _RULE_1_MONTHLY_BASE,
    _RULE_2_SELIC_SHARE,
)


class TestRamoSelicAlta:
    """SELIC > 8,5% a.a. → 0,5% a.m. + TR."""

    def test_selic_high_tr_zero(self):
        result = calculate_savings_rate(selic_annual=0.1475, tr_monthly=0.0)
        assert result.rule_branch == "SELIC_GT_8_5"
        assert result.savings_monthly == pytest.approx(0.005)

    def test_selic_high_tr_positive(self):
        result = calculate_savings_rate(selic_annual=0.1475, tr_monthly=0.0015)
        assert result.rule_branch == "SELIC_GT_8_5"
        # TR soma diretamente ao 0,5% base nesse ramo
        assert result.savings_monthly == pytest.approx(0.005 + 0.0015)

    def test_selic_annual_e_tr_repassados_sem_alteracao(self):
        result = calculate_savings_rate(selic_annual=0.20, tr_monthly=0.001)
        assert result.selic_annual == pytest.approx(0.20)
        assert result.tr_monthly == pytest.approx(0.001)


class TestRamoSelicBaixa:
    """SELIC <= 8,5% a.a. → 70% da SELIC mensalizada + TR."""

    def test_selic_low_tr_zero(self):
        selic_annual = 0.07
        result = calculate_savings_rate(selic_annual=selic_annual, tr_monthly=0.0)
        assert result.rule_branch == "SELIC_LTE_8_5"

        selic_monthly_esperado = (1 + selic_annual) ** (1 / 12) - 1
        assert result.savings_monthly == pytest.approx(
            0.70 * selic_monthly_esperado, rel=1e-4
        )

    def test_selic_low_tr_positive_soma_tr(self):
        selic_annual = 0.05
        tr_monthly = 0.002
        result = calculate_savings_rate(selic_annual=selic_annual, tr_monthly=tr_monthly)

        selic_monthly_esperado = (1 + selic_annual) ** (1 / 12) - 1
        esperado = 0.70 * selic_monthly_esperado + tr_monthly
        assert result.savings_monthly == pytest.approx(esperado, rel=1e-4)


class TestFronteiraExata8_5:
    def test_selic_exatamente_8_5_usa_ramo_baixo(self):
        """A regra usa '> 8,5%' para o ramo alto — 8,5% exato cai no ramo de
        70% da SELIC, não no de 0,5% fixo (checar fonte oficial antes do
        merge, ver docstring do módulo)."""
        result = calculate_savings_rate(selic_annual=_SELIC_THRESHOLD_ANNUAL, tr_monthly=0.0)
        assert result.rule_branch == "SELIC_LTE_8_5"

    def test_um_ponto_base_acima_da_fronteira_usa_ramo_alto(self):
        result = calculate_savings_rate(selic_annual=_SELIC_THRESHOLD_ANNUAL + 0.0001, tr_monthly=0.0)
        assert result.rule_branch == "SELIC_GT_8_5"


class TestAnualizacaoPorComposicao:
    def test_savings_annual_e_composicao_mensal_nao_multiplicacao_simples(self):
        result = calculate_savings_rate(selic_annual=0.1475, tr_monthly=0.0)
        # abs (não rel): savings_annual é arredondado para 6 casas dentro da
        # função, o que já introduz um erro maior que uma tolerância relativa apertada
        esperado = (1 + result.savings_monthly) ** 12 - 1
        assert result.savings_annual == pytest.approx(esperado, abs=1e-6)
        # nao deveria ser igual a uma simples multiplicacao por 12
        assert result.savings_annual != pytest.approx(result.savings_monthly * 12, rel=1e-6)


class TestSourceRepassado:
    def test_source_default_e_bacen(self):
        result = calculate_savings_rate(selic_annual=0.1475, tr_monthly=0.0)
        assert result.source == "BACEN"

    def test_source_fallback_repassado(self):
        result = calculate_savings_rate(selic_annual=0.1475, tr_monthly=0.0, source="FALLBACK")
        assert result.source == "FALLBACK"


class TestConstantesDaRegra:
    """Trava de regressão: mudar esses números é uma decisão jurídica, não um refactor."""

    def test_constantes_atuais(self):
        assert _SELIC_THRESHOLD_ANNUAL == pytest.approx(0.085)
        assert _RULE_1_MONTHLY_BASE == pytest.approx(0.005)
        assert _RULE_2_SELIC_SHARE == pytest.approx(0.70)
