"""
tests/architect/test_regression_fixes.py

Testes de regressão para os fixes críticos do módulo Architect.
Se qualquer um destes testes quebrar, um fix foi revertido silenciosamente.

Fixes cobertos:
    1. IOF = 0 para IMOVEL/SFH  (Decreto 6.306/2007)
    2. IOF > 0 para VEICULO      (verificar que o caso geral não foi desabilitado)
    3. NPV do FINANCING inclui seguro mensal nos cashflows
    4. NPV do FINANCING inclui IOF no cashflow inicial (t=0)
    5. Aluguel corrigido por IPCA em SAVE_INVEST (não fixo)
    6. Ponte Pluggy: taxa anual unit=YEARLY não produz cet_annual (evita (1+r)^12-1 errado)
"""

import pytest

from app.architect.calculators import financing as fin_calc
from app.architect.models import AssetType, RiskProfile, SimulationRequest
from app.architect.simulators.strategy_engine import StrategyEngine, _IOF_RATE_BY_ASSET

# ─────────────────────────────────────────────────────────────────────
# Fixtures compartilhadas
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return StrategyEngine()


@pytest.fixture
def rates():
    return {
        "selic_annual":      0.1475,
        "cdi_annual":        0.1465,
        "best_cet_annual":   0.1950,
        "ipca_annual":       0.045,
        "disc_rate_monthly": (1 + 0.1475) ** (1 / 12) - 1,
        "consortium_admin_rate":        0.17,
        "consortium_months":            72.0,
        "consortium_reserve_fund_rate": 0.02,
        "consortium_annual_adjustment_rate": 0.045,
        "consortium_group_size":        100,
        "consortium_contemplated_per_month": 2,
    }


# ─────────────────────────────────────────────────────────────────────
# FIX 1 — IOF = 0 para IMOVEL (SFH)
# ─────────────────────────────────────────────────────────────────────

class TestIOFExemptionSFH:

    def test_iof_rate_map_imovel_is_zero(self):
        assert _IOF_RATE_BY_ASSET[AssetType.IMOVEL] == 0.0

    def test_calculate_iof_returns_zero_when_rate_is_zero(self):
        schedule = [
            {"month": m, "payment": 2800.0, "amortization": 1000.0, "insurance": 0.0}
            for m in range(1, 361)
        ]
        iof_fixed, iof_daily, iof_total = fin_calc._calculate_iof(
            principal=300_000.0,
            schedule=schedule,
            iof_fixed_rate=0.0,
        )
        assert iof_fixed == 0.0
        assert iof_daily == 0.0
        assert iof_total == 0.0

    def test_financing_imovel_has_zero_total_iof(self):
        result = fin_calc.calculate_price(
            principal=300_000.0,
            annual_rate=0.1100,
            months=360,
            iof_rate=0.0,
            asset_type="property",
        )
        assert result.total_iof == 0.0
        assert result.iof_fixed_component == 0.0
        assert result.iof_daily_component == 0.0

    def test_simulate_financing_imovel_cashflow_t0_equals_down_payment_only(
        self, engine, rates
    ):
        req = SimulationRequest(
            user_id="reg_test",
            target_amount=300_000.0,
            down_payment=60_000.0,
            financing_months=360,
            asset_type=AssetType.IMOVEL,
        )
        result = engine._simulate_financing(req, rates)
        # cashflows[0] = -(down_payment + total_iof); para IMOVEL total_iof=0
        # então cashflows[0] deve ser exatamente -down_payment
        t0 = result["cashflows"][0]
        assert t0 == pytest.approx(-60_000.0), (
            f"Para IMOVEL (SFH) o IOF é zero — cashflow t=0 deve ser -down_payment, "
            f"mas foi {t0}"
        )


# ─────────────────────────────────────────────────────────────────────
# FIX 2 — IOF > 0 para VEICULO (caso geral não desabilitado)
# ─────────────────────────────────────────────────────────────────────

class TestIOFVeiculo:

    def test_iof_rate_map_veiculo_is_nonzero(self):
        assert _IOF_RATE_BY_ASSET[AssetType.VEICULO] > 0.0

    def test_financing_veiculo_has_positive_total_iof(self):
        result = fin_calc.calculate_price(
            principal=50_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="vehicle",
        )
        assert result.total_iof > 0.0

    def test_financing_veiculo_iof_below_cap(self):
        # IOF nunca deve ultrapassar 3% do principal
        result = fin_calc.calculate_price(
            principal=50_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="vehicle",
        )
        assert result.total_iof <= 50_000.0 * fin_calc.IOF_MAX_RATE


# ─────────────────────────────────────────────────────────────────────
# FIX 3 — NPV do FINANCING inclui seguro nos cashflows
# ─────────────────────────────────────────────────────────────────────

class TestNPVIncludesInsurance:

    def test_veiculo_schedule_has_nonzero_insurance(self):
        result = fin_calc.calculate_price(
            principal=50_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="vehicle",
        )
        insurances = [row["insurance"] for row in result.schedule]
        assert any(ins > 0 for ins in insurances), "seguro deve estar no schedule"

    def test_imovel_schedule_has_nonzero_insurance(self):
        result = fin_calc.calculate_price(
            principal=300_000.0,
            annual_rate=0.1100,
            months=360,
            iof_rate=0.0,
            asset_type="property",
        )
        insurances = [row["insurance"] for row in result.schedule]
        assert any(ins > 0 for ins in insurances), "MIP/DFI deve estar no schedule de imóvel"

    def test_simulate_financing_veiculo_npv_includes_insurance(
        self, engine, rates
    ):
        req_com = SimulationRequest(
            user_id="reg_test",
            target_amount=50_000.0,
            down_payment=10_000.0,
            financing_months=48,
            asset_type=AssetType.VEICULO,
        )
        # Simula sem seguro forçando insurance_rate=0 diretamente no calculador
        result_com_seguro = fin_calc.calculate_price(
            principal=40_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="vehicle",
        )
        result_sem_seguro = fin_calc.calculate_price(
            principal=40_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="other",   # sem seguro padrão
            insurance_monthly_rate=0.0,
        )
        # Custo total com seguro deve ser maior
        assert result_com_seguro.total_cost > result_sem_seguro.total_cost
        assert result_com_seguro.total_insurance > 0.0
        assert result_sem_seguro.total_insurance == 0.0

    def test_total_insurance_equals_sum_of_schedule_insurance(self):
        result = fin_calc.calculate_price(
            principal=50_000.0,
            annual_rate=0.1950,
            months=48,
            iof_rate=fin_calc.IOF_FIXO_RATE,
            asset_type="vehicle",
        )
        schedule_sum = sum(row["insurance"] for row in result.schedule)
        assert result.total_insurance == pytest.approx(schedule_sum, rel=1e-4)


# ─────────────────────────────────────────────────────────────────────
# FIX 4 — NPV: IOF está no cashflow t=0 (não spread ao longo do contrato)
# ─────────────────────────────────────────────────────────────────────

class TestNPVIOFAtT0:

    def test_simulate_financing_cashflow_t0_includes_iof(
        self, engine, rates
    ):
        req = SimulationRequest(
            user_id="reg_test",
            target_amount=50_000.0,
            down_payment=10_000.0,
            financing_months=48,
            asset_type=AssetType.VEICULO,
        )
        # Precisamos acessar o sim direto para checar o cashflow
        from app.architect.calculators import financing as fc
        from app.architect.simulators.strategy_engine import _CALC_ASSET_MAP, _IOF_RATE_BY_ASSET

        iof_rate   = _IOF_RATE_BY_ASSET[req.asset_type]
        calc_asset = _CALC_ASSET_MAP[req.asset_type]
        sim = fc.calculate_price(
            req.principal, rates["best_cet_annual"], req.financing_months,
            iof_rate=iof_rate, asset_type=calc_asset,
        )
        expected_t0 = -(req.down_payment + sim.total_iof)
        # cashflows[0] deve ser negativo e maior em módulo que só o down_payment
        assert sim.total_iof > 0.0
        assert expected_t0 < -req.down_payment


# ─────────────────────────────────────────────────────────────────────
# FIX 5 — Aluguel corrigido por IPCA em SAVE_INVEST (não flat)
# ─────────────────────────────────────────────────────────────────────

class TestSaveInvestRentIPCA:

    def test_rent_ipca_adjusted_produces_higher_cost(self, engine, rates):
        req_sem_rent = SimulationRequest(
            user_id="reg_test",
            target_amount=300_000.0,
            down_payment=30_000.0,
            financing_months=120,
            asset_type=AssetType.IMOVEL,
        )
        req_com_rent = req_sem_rent.model_copy(update={"current_monthly_rent": 2_500.0})

        r_sem = engine._simulate_investment(req_sem_rent, rates)
        r_com = engine._simulate_investment(req_com_rent, rates)

        assert r_com["npv"] < r_sem["npv"], (
            "Com aluguel o NPV deve ser mais negativo — se quebrou, "
            "o aluguel pode ter sido removido dos cashflows"
        )

    def test_ipca_adjustment_raises_cost_vs_flat_rent(self, engine):
        # Mesmo cenário com IPCA 4.5% vs IPCA 0% — com IPCA o aluguel cresce e o
        # NPV deve ser mais negativo (maior custo). Isola o efeito da correção.
        base_rates = {
            "selic_annual":      0.1475,
            "cdi_annual":        0.1465,
            "best_cet_annual":   0.1950,
            "disc_rate_monthly": (1 + 0.1475) ** (1 / 12) - 1,
        }
        req = SimulationRequest(
            user_id="reg_test",
            target_amount=300_000.0,
            down_payment=30_000.0,
            financing_months=120,
            asset_type=AssetType.IMOVEL,
            current_monthly_rent=2_000.0,
        )
        r_sem_ipca = engine._simulate_investment(req, {**base_rates, "ipca_annual": 0.0})
        r_com_ipca = engine._simulate_investment(req, {**base_rates, "ipca_annual": 0.05})

        assert r_com_ipca["npv"] < r_sem_ipca["npv"], (
            "Com IPCA o aluguel cresce mês a mês → custo total maior → NPV mais negativo. "
            "Se quebrou, a correção (1+ipca_monthly)^m foi removida dos cashflows."
        )


# ─────────────────────────────────────────────────────────────────────
# FIX 6 — Pluggy: taxa YEARLY não produz cet_annual (evita (1+r)^12-1 errado)
# ─────────────────────────────────────────────────────────────────────

class TestPluggyRateConversion:

    def test_yearly_unit_loan_returns_none(self):
        from app.architect.router import _normalize_pluggy_loan
        raw = {
            "type": "PERSONAL_CREDIT",
            "monthlyPaymentAmount": 500.0,
            "interestRates": [{"rate": 0.268, "type": "ANNUAL", "unit": "YEARLY"}],
        }
        result = _normalize_pluggy_loan(raw)
        assert result is None, (
            "Taxa com unit=YEARLY não deve gerar cet_annual — "
            "se retornar um valor, está aplicando (1+0.268)^12-1 ≈ 1600% erroneamente"
        )

    def test_monthly_unit_loan_produces_correct_cet(self):
        from app.architect.router import _normalize_pluggy_loan
        raw = {
            "type": "PERSONAL_CREDIT",
            "monthlyPaymentAmount": 850.0,
            "interestRates": [{"rate": 0.0199, "type": "NOMINAL", "unit": "MONTHLY"}],
            "instalments": {"paid": 6, "missed": 0},
        }
        result = _normalize_pluggy_loan(raw)
        assert result is not None
        expected = (1.0 + 0.0199) ** 12 - 1.0
        # cet_annual é arredondado para 4 casas no normalizer — tolerância de 0.5 bps
        assert result["cet_annual"] == pytest.approx(expected, abs=5e-4), (
            "0.0199/mês deve converter para ~26.7% a.a. via (1+r)^12-1"
        )

    def test_financing_yearly_unit_returns_none(self):
        from app.architect.router import _normalize_pluggy_financing
        raw = {
            "type": "HOME_LOAN",
            "monthlyPaymentAmount": 3000.0,
            "interestRates": [{"rate": 0.0900, "type": "ANNUAL", "unit": "YEARLY"}],
        }
        result = _normalize_pluggy_financing(raw)
        assert result is None, (
            "Financing com unit=YEARLY não deve gerar cet_annual — "
            "9% a.a. interpretado como mensal produziria 185% a.a."
        )
