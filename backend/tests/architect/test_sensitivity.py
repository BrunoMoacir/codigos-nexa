"""
tests/architect/test_sensitivity.py

Testes unitários do SensitivityAnalyzer da F3 (Fase 3).

Cobre:
    - Estrutura do SensitivityReport (campos, tipos, intervalos válidos)
    - Curvas de cada variável (interest_rate, months, down_payment, cdi_rate)
    - Métricas agregadas (npv_range, elasticity, strategy_flips)
    - Comportamento sem consórcio (include_consortium=False)
    - Helpers puros (_linspace, _pick_strategy, _compute_risk_profile)
    - Serialização to_dict()
    - Casos-limite (down_payment zero, budget ausente)
"""

import sys
from pathlib import Path
from datetime import datetime

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.architect.models import (
    ActionStep,
    AmortizationMethod,
    AssetType,
    CostScenario,
    NPVComparison,
    RiskProfile,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)
from app.architect.simulators.sensitivity_analyzer import (
    SensitivityAnalyzer,
    SensitivityPoint,
    SensitivityReport,
    VariableSensitivity,
    _compute_risk_profile,
    _linspace,
    _pick_strategy,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture
def analyzer():
    return SensitivityAnalyzer()


@pytest.fixture
def market_rates():
    """Taxas base para fevereiro/2026."""
    return {
        "selic_annual":               0.1325,
        "cdi_annual":                 0.1315,
        "best_cet_annual":            0.1950,
        "consortium_admin_rate":      0.17,
        "consortium_months":          72,
        "consortium_reserve_fund_rate": 0.02,
    }


@pytest.fixture
def base_request():
    """Request padrão: veículo R$50k, entrada R$10k, budget R$2k."""
    return SimulationRequest(
        user_id="test_sensitivity_001",
        target_amount=50_000.0,
        down_payment=10_000.0,
        max_monthly_budget=2_000.0,
        risk_profile=RiskProfile.MODERADO,
        asset_type=AssetType.VEICULO,
        include_consortium=True,
        financing_months=48,
        amortization_method=AmortizationMethod.PRICE,
    )


@pytest.fixture
def imovel_request():
    """Request imóvel R$350k — SAC, prazo longo."""
    return SimulationRequest(
        user_id="test_sensitivity_002",
        target_amount=350_000.0,
        down_payment=70_000.0,
        max_monthly_budget=3_500.0,
        risk_profile=RiskProfile.CONSERVADOR,
        asset_type=AssetType.IMOVEL,
        include_consortium=True,
        financing_months=240,
        amortization_method=AmortizationMethod.SAC,
    )


@pytest.fixture
def request_sem_consortium():
    """Request com include_consortium=False."""
    return SimulationRequest(
        user_id="test_sensitivity_003",
        target_amount=30_000.0,
        down_payment=5_000.0,
        max_monthly_budget=1_500.0,
        include_consortium=False,
        financing_months=36,
    )


@pytest.fixture
def request_sem_down_payment():
    """Request sem valor de entrada."""
    return SimulationRequest(
        user_id="test_sensitivity_004",
        target_amount=80_000.0,
        down_payment=0.0,
        max_monthly_budget=3_000.0,
        include_consortium=True,
        financing_months=60,
    )


def _fake_response(strategy: StrategyType = StrategyType.SAVE_INVEST) -> SimulationResponse:
    """Monta um SimulationResponse mínimo para usar como baseline."""
    return SimulationResponse(
        recommended_strategy=strategy,
        costs=CostScenario(min_cost=45_000, expected_cost=50_000, max_cost=55_000),
        npv=NPVComparison(
            financing=-42_000.0,
            save_invest=-38_000.0,
            discount_rate_used=0.01035,
        ),
        liquidity_impact=-0.25,
        months_to_achieve=48,
        action_plan=[ActionStep(step=1, action="Abrir conta investimento", is_critical=True)],
        confidence_score=0.82,
        data_sources=["bacen", "anbima"],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESTRUTURA DO RELATÓRIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSensitivityReportStructure:
    """Verifica que o relatório tem a estrutura esperada."""

    def test_analyze_retorna_sensitivity_report(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        assert isinstance(report, SensitivityReport)

    def test_report_tem_quatro_variaveis(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        assert len(report.variables) == 4

    def test_variaveis_conhecidas_presentes(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        nomes = {v.variable for v in report.variables}
        assert nomes == {"interest_rate", "months", "down_payment", "cdi_rate"}

    def test_most_sensitive_e_uma_das_variaveis(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        nomes = {v.variable for v in report.variables}
        assert report.most_sensitive_variable in nomes

    def test_risk_profile_valido(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        assert report.risk_profile in {"baixo", "moderado", "alto"}

    def test_strategy_stability_entre_zero_e_um(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        assert 0.0 <= report.strategy_stability <= 1.0

    def test_baseline_strategy_reflete_response(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(
            base_request, market_rates, _fake_response(StrategyType.FINANCING)
        )
        assert report.baseline_strategy == StrategyType.FINANCING.value

    def test_generated_at_e_datetime(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        assert isinstance(report.generated_at, datetime)

    def test_variaveis_ordenadas_por_impacto_decrescente(
        self, analyzer, base_request, market_rates
    ):
        """Variável com maior npv_range deve vir primeiro."""
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        ranges = [v.npv_range for v in report.variables]
        assert ranges == sorted(ranges, reverse=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CURVAS DE SENSIBILIDADE — PONTOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSensitivityPoints:
    """Verifica a estrutura dos pontos em cada curva."""

    def _get_variable(self, report: SensitivityReport, name: str) -> VariableSensitivity:
        return next(v for v in report.variables if v.variable == name)

    def test_interest_rate_tem_9_pontos(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        v = self._get_variable(report, "interest_rate")
        assert len(v.points) == 9

    def test_months_tem_7_pontos(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        v = self._get_variable(report, "months")
        assert len(v.points) == 7

    def test_down_payment_tem_9_pontos(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        v = self._get_variable(report, "down_payment")
        assert len(v.points) == 9

    def test_cdi_rate_tem_9_pontos(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        v = self._get_variable(report, "cdi_rate")
        assert len(v.points) == 9

    def test_pontos_cobrem_range_completo(
        self, analyzer, base_request, market_rates
    ):
        """Delta mínimo e máximo devem estar nos extremos do range."""
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            deltas = [p.delta for p in v.points]
            assert deltas[0] < 0, f"{v.variable}: primeiro delta deve ser negativo"
            assert deltas[-1] > 0, f"{v.variable}: último delta deve ser positivo"

    def test_pontos_tem_recommended_valido(
        self, analyzer, base_request, market_rates
    ):
        """O campo recommended deve ser um StrategyType válido."""
        valid = {st.value for st in StrategyType}
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            for p in v.points:
                assert p.recommended in valid, (
                    f"{v.variable}: recommended='{p.recommended}' inválido"
                )

    def test_npv_financing_e_invest_sao_floats(
        self, analyzer, base_request, market_rates
    ):
        """NPV do financiamento e investimento nunca devem ser None."""
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            for p in v.points:
                assert isinstance(p.npv_financing, float)
                assert isinstance(p.npv_invest, float)

    def test_consortium_presente_quando_habilitado(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            for p in v.points:
                assert p.npv_consortium is not None, (
                    f"{v.variable}: npv_consortium não deve ser None quando consórcio habilitado"
                )

    def test_consortium_ausente_quando_desabilitado(
        self, analyzer, request_sem_consortium, market_rates
    ):
        report = analyzer.analyze(
            request_sem_consortium, market_rates, _fake_response()
        )
        for v in report.variables:
            for p in v.points:
                assert p.npv_consortium is None, (
                    f"{v.variable}: npv_consortium deve ser None quando consórcio desabilitado"
                )

    def test_param_value_varia_monotonicamente(
        self, analyzer, base_request, market_rates
    ):
        """param_value deve aumentar da esquerda para direita."""
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            values = [p.param_value for p in v.points]
            assert values == sorted(values), (
                f"{v.variable}: param_value não é crescente"
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MÉTRICAS AGREGADAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSensitivityMetrics:
    """Verifica npv_range, elasticity e strategy_flips."""

    def test_npv_range_nao_negativo(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            assert v.npv_range >= 0, f"{v.variable}: npv_range negativo"

    def test_elasticity_nao_negativa(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            assert v.elasticity >= 0, f"{v.variable}: elasticity negativa"

    def test_strategy_flips_valido(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        for v in report.variables:
            max_possivel = len(v.points) - 1
            assert 0 <= v.strategy_flips <= max_possivel, (
                f"{v.variable}: strategy_flips={v.strategy_flips} fora do intervalo [0, {max_possivel}]"
            )

    def test_most_sensitive_tem_maior_npv_range(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        melhor = max(report.variables, key=lambda v: v.npv_range)
        assert report.most_sensitive_variable == melhor.variable

    def test_base_value_coerente_com_request(
        self, analyzer, base_request, market_rates
    ):
        """base_value de months deve coincidir com request.financing_months."""
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        months_var = next(v for v in report.variables if v.variable == "months")
        assert months_var.base_value == float(base_request.financing_months)

    def test_base_value_down_payment_coerente(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        dp_var = next(v for v in report.variables if v.variable == "down_payment")
        assert dp_var.base_value == base_request.down_payment


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASOS-LIMITE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestEdgeCases:
    """Casos-limite: down_payment zero, sem budget, imóvel caro."""

    def test_down_payment_zero_nao_crasha(
        self, analyzer, request_sem_down_payment, market_rates
    ):
        report = analyzer.analyze(
            request_sem_down_payment, market_rates, _fake_response()
        )
        assert isinstance(report, SensitivityReport)
        assert len(report.variables) == 4

    def test_request_sem_budget_funciona(
        self, analyzer, market_rates
    ):
        req = SimulationRequest(
            user_id="test_no_budget",
            target_amount=60_000.0,
            down_payment=5_000.0,
            financing_months=48,
            include_consortium=True,
        )
        report = analyzer.analyze(req, market_rates, _fake_response())
        assert isinstance(report, SensitivityReport)

    def test_imovel_request_funciona(
        self, analyzer, imovel_request, market_rates
    ):
        report = analyzer.analyze(imovel_request, market_rates, _fake_response())
        assert isinstance(report, SensitivityReport)
        assert report.risk_profile in {"baixo", "moderado", "alto"}

    def test_sem_consortium_tem_strategy_stability_valida(
        self, analyzer, request_sem_consortium, market_rates
    ):
        report = analyzer.analyze(
            request_sem_consortium, market_rates, _fake_response()
        )
        assert 0.0 <= report.strategy_stability <= 1.0

    def test_taxas_minimas_nao_crasham(
        self, analyzer, base_request
    ):
        """Taxa SELIC/CDI próximas de zero não devem causar divisão por zero."""
        rates_minimas = {
            "selic_annual":               0.001,
            "cdi_annual":                 0.001,
            "best_cet_annual":            0.05,
            "consortium_admin_rate":      0.15,
            "consortium_months":          60,
            "consortium_reserve_fund_rate": 0.01,
        }
        report = analyzer.analyze(base_request, rates_minimas, _fake_response())
        assert isinstance(report, SensitivityReport)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS PUROS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLinspace:
    """Testa o helper _linspace (equivalente ao numpy.linspace)."""

    def test_cinco_pontos_entre_zero_e_um(self):
        result = _linspace(0.0, 1.0, 5)
        assert len(result) == 5
        assert abs(result[0] - 0.0) < 1e-9
        assert abs(result[-1] - 1.0) < 1e-9
        assert abs(result[2] - 0.5) < 1e-9

    def test_um_ponto_retorna_start(self):
        result = _linspace(-0.02, 0.02, 1)
        assert result == [-0.02]

    def test_dois_pontos_retorna_extremos(self):
        result = _linspace(-1.0, 1.0, 2)
        assert len(result) == 2
        assert abs(result[0] - (-1.0)) < 1e-9
        assert abs(result[1] - 1.0) < 1e-9

    def test_nove_pontos_range_taxa(self):
        """Range ±2 p.p. em 9 pontos = step de 0.5 p.p."""
        result = _linspace(-0.02, 0.02, 9)
        assert len(result) == 9
        assert abs(result[0] - (-0.02)) < 1e-9
        assert abs(result[4] - 0.0) < 1e-9     # ponto central = 0
        assert abs(result[-1] - 0.02) < 1e-9

    def test_sete_pontos_range_meses(self):
        result = _linspace(-6.0, 6.0, 7)
        assert len(result) == 7
        assert abs(result[3] - 0.0) < 1e-9     # centro deve ser 0


class TestPickStrategy:
    """Testa o helper _pick_strategy."""

    def test_financing_maior_vence(self):
        assert _pick_strategy(-50_000, -70_000, -80_000) == StrategyType.FINANCING.value

    def test_invest_maior_vence(self):
        assert _pick_strategy(-80_000, -60_000, -70_000) == StrategyType.SAVE_INVEST.value

    def test_consortium_maior_vence(self):
        assert _pick_strategy(-90_000, -85_000, -75_000) == StrategyType.CONSORTIUM.value

    def test_sem_consortium_ignora_none(self):
        result = _pick_strategy(-60_000, -50_000, None)
        assert result == StrategyType.SAVE_INVEST.value

    def test_sem_consortium_financing_vence(self):
        result = _pick_strategy(-40_000, -50_000, None)
        assert result == StrategyType.FINANCING.value


class TestComputeRiskProfile:
    """Testa o helper _compute_risk_profile (elasticidade normalizada pelo target)."""

    TARGET = 100_000.0

    def test_zero_flips_baixa_elasticity_pct_retorna_baixo(self):
        # 5k / 100k = 5% < 20% → baixo
        assert _compute_risk_profile(0, 5_000, self.TARGET) == "baixo"

    def test_zero_flips_elasticity_pct_limite_baixo(self):
        # 19.999k / 100k = ~20% → baixo (abaixo do limiar)
        assert _compute_risk_profile(0, 19_999, self.TARGET) == "baixo"

    def test_zero_flips_elasticity_pct_acima_limite_retorna_moderado(self):
        # 20.001k / 100k = ~20% → moderado (acima do limiar)
        assert _compute_risk_profile(0, 20_001, self.TARGET) == "moderado"

    def test_dois_flips_elasticity_pct_moderada_retorna_moderado(self):
        # 2 flips, 50k / 100k = 50% < 100% → moderado
        assert _compute_risk_profile(2, 50_000, self.TARGET) == "moderado"

    def test_tres_flips_retorna_alto(self):
        # 3 flips > 2 → alto independente de elasticidade
        assert _compute_risk_profile(3, 50_000, self.TARGET) == "alto"

    def test_muitos_flips_retorna_alto(self):
        assert _compute_risk_profile(8, 500_000, self.TARGET) == "alto"

    def test_elasticity_pct_acima_de_cem_pct_retorna_alto(self):
        # 100.001k / 100k = 100% ≥ 100% → alto
        assert _compute_risk_profile(0, 100_001, self.TARGET) == "alto"

    def test_normaliza_por_target_grande(self):
        # mesma elasticidade absoluta, target 10× maior → "baixo" em vez de "alto"
        assert _compute_risk_profile(0, 100_001, 1_000_000.0) == "baixo"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SERIALIZAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSensitivityToDict:
    """Verifica a saída do método to_dict()."""

    def test_to_dict_retorna_dict(self, analyzer, base_request, market_rates):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_tem_campos_obrigatorios(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        obrigatorios = {
            "variables",
            "most_sensitive_variable",
            "strategy_stability",
            "risk_profile",
            "baseline_strategy",
            "generated_at",
        }
        assert obrigatorios <= set(d.keys())

    def test_to_dict_variables_tem_campos_obrigatorios(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        campos = {"variable", "description", "unit", "base_value",
                  "npv_range", "elasticity", "strategy_flips", "points"}
        for v in d["variables"]:
            assert campos <= set(v.keys())

    def test_to_dict_points_tem_campos_obrigatorios(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        campos = {"delta", "param_value", "npv_financing", "npv_invest",
                  "npv_consortium", "recommended"}
        for v in d["variables"]:
            for p in v["points"]:
                assert campos <= set(p.keys())

    def test_to_dict_generated_at_e_string_iso(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        assert isinstance(d["generated_at"], str)
        # deve ser parseável como ISO datetime
        datetime.fromisoformat(d["generated_at"])

    def test_to_dict_strategy_stability_e_float(
        self, analyzer, base_request, market_rates
    ):
        report = analyzer.analyze(base_request, market_rates, _fake_response())
        d = report.to_dict()
        assert isinstance(d["strategy_stability"], float)
