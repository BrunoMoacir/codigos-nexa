# tests/fiscal/test_tesouro_selic.py
"""
OPP.3 — IRPFCalculator.calc_ir_on_tesouro_selic (docs/OPP.md §5.2):
IR regressivo (mesma tabela do CDB) + custódia B3 de 0,20% a.a. sobre o
estoque excedente a R$10.000.
"""
import pytest

from app.fiscal.ir_pf_calculator import IRPFCalculator


@pytest.fixture
def calc():
    return IRPFCalculator()


class TestCustodiaB3:
    def test_abaixo_de_10k_nao_paga_custodia(self, calc):
        """Até R$10k o Tesouro Selic é isento de custódia — líquido igual a
        um CDB 'a 100% da SELIC' com mesma alíquota."""
        tesouro = calc.calc_ir_on_tesouro_selic(5_000, 0.15, 12)
        cdb_equivalente = calc.calc_ir_on_cdb(5_000, 15.0, 12)
        assert tesouro.net_yield_brl == pytest.approx(cdb_equivalente.net_yield_brl, abs=0.5)

    def test_acima_de_10k_paga_custodia_sobre_o_excedente(self, calc):
        tesouro = calc.calc_ir_on_tesouro_selic(50_000, 0.15, 12)
        cdb_equivalente = calc.calc_ir_on_cdb(50_000, 15.0, 12)
        assert tesouro.net_yield_brl < cdb_equivalente.net_yield_brl
        # custódia ~0,20% sobre ~R$43k de excedente médio ≈ R$87 no ano
        diff = cdb_equivalente.net_yield_brl - tesouro.net_yield_brl
        assert 40.0 < diff < 120.0

    def test_custodia_zero_quando_fee_zero(self, calc):
        sem_fee = calc.calc_ir_on_tesouro_selic(50_000, 0.15, 12, custody_fee_annual=0.0)
        cdb = calc.calc_ir_on_cdb(50_000, 15.0, 12)
        assert sem_fee.net_yield_brl == pytest.approx(cdb.net_yield_brl, abs=0.5)


class TestIRRegressivo:
    def test_aliquota_segue_tabela_regressiva(self, calc):
        assert calc.calc_ir_on_tesouro_selic(10_000, 0.15, 5).ir_rate == 0.225
        assert calc.calc_ir_on_tesouro_selic(10_000, 0.15, 12).ir_rate == 0.200
        assert calc.calc_ir_on_tesouro_selic(10_000, 0.15, 24).ir_rate == 0.175
        assert calc.calc_ir_on_tesouro_selic(10_000, 0.15, 36).ir_rate == 0.150

    def test_investment_type_e_nao_isento(self, calc):
        result = calc.calc_ir_on_tesouro_selic(10_000, 0.15, 12)
        assert result.investment_type == "TESOURO_SELIC"
        assert result.is_exempt is False
        assert result.ir_brl > 0


class TestTaxaLiquida:
    def test_net_annual_rate_menor_que_selic_bruta(self, calc):
        result = calc.calc_ir_on_tesouro_selic(10_000, 0.15, 12)
        assert 0 < result.net_annual_rate_pct < 15.0

    def test_prazo_maior_melhora_taxa_liquida(self, calc):
        """Alíquota cai de 20% (12m) para 15% (36m) — taxa líquida sobe."""
        r12 = calc.calc_ir_on_tesouro_selic(10_000, 0.15, 12)
        r36 = calc.calc_ir_on_tesouro_selic(10_000, 0.15, 36)
        assert r36.net_annual_rate_pct > r12.net_annual_rate_pct
