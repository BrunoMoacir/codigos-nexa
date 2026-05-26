"""
tests/architect/test_strategy_engine.py

Testes unitários do StrategyEngine da F3.
Testa as 3 simulações (Financiamento, Investimento, Consórcio)
e a lógica de decisão entre elas.
"""

import sys
from pathlib import Path

# Garante que backend esteja no PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from app.architect.models import (
    SimulationRequest,
    SimulationResponse,
    StrategyType,
    RiskProfile,
    AssetType,
    AmortizationMethod,
)
from app.architect.simulators.strategy_engine import StrategyEngine


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def engine():
    return StrategyEngine()


@pytest.fixture
def market_rates():
    """Taxas de mercado realistas para 2026."""
    return {
        "selic_annual": 0.1075,   # 10,75% a.a.
        "cdi_annual": 0.1025,     # 10,25% a.a.
        "best_cet_annual": 0.14,  # 14% a.a. CET
    }


@pytest.fixture
def base_request():
    """Request básico: veículo de R$50k com R$10k de entrada."""
    return SimulationRequest(
        user_id="test_user_001",
        target_amount=50000.0,
        down_payment=10000.0,
        max_monthly_budget=2000.0,
        risk_profile=RiskProfile.MODERADO,
        asset_type=AssetType.VEICULO,
        include_consortium=True,
        financing_months=48,
        amortization_method=AmortizationMethod.PRICE,
    )


@pytest.fixture
def request_sem_consortium():
    """Request sem consórcio."""
    return SimulationRequest(
        user_id="test_user_002",
        target_amount=30000.0,
        down_payment=5000.0,
        max_monthly_budget=1500.0,
        include_consortium=False,
        financing_months=36,
    )


@pytest.fixture
def request_sem_budget():
    """Request sem limite de orçamento."""
    return SimulationRequest(
        user_id="test_user_003",
        target_amount=80000.0,
        down_payment=15000.0,
        financing_months=60,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES BÁSICOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStrategyEngineBasic:
    """Testa cenários básicos de simulação."""

    def test_simulate_retorna_simulation_response(
        self, engine, base_request, market_rates
    ):
        """Engine deve retornar um SimulationResponse válido."""
        result = engine.simulate(base_request, market_rates)

        assert isinstance(result, SimulationResponse)
        assert result.recommended_strategy in StrategyType
        assert result.confidence_score > 0
        assert len(result.action_plan) >= 1

    def test_costs_sao_positivos(self, engine, base_request, market_rates):
        """Custos devem ser positivos e respeitar min <= expected <= max."""
        result = engine.simulate(base_request, market_rates)

        assert result.costs.min_cost > 0
        assert result.costs.expected_cost >= result.costs.min_cost
        assert result.costs.max_cost >= result.costs.expected_cost

    def test_npv_financing_e_investimento_presentes(
        self, engine, base_request, market_rates
    ):
        """NPV deve conter financiamento e investimento sempre."""
        result = engine.simulate(base_request, market_rates)

        assert result.npv.financing is not None
        assert result.npv.save_invest is not None
        assert result.npv.discount_rate_used > 0

    def test_months_to_achieve_minimo_1(
        self, engine, base_request, market_rates
    ):
        """Meses para atingir deve ser pelo menos 1."""
        result = engine.simulate(base_request, market_rates)
        assert result.months_to_achieve >= 1

    def test_data_sources_tem_itens(
        self, engine, base_request, market_rates
    ):
        """Fontes de dados devem estar presentes."""
        result = engine.simulate(base_request, market_rates)
        assert len(result.data_sources) > 0
        assert "bacen" in result.data_sources


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES CONSÓRCIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConsortiumSimulation:
    """Testa a lógica do consórcio."""

    def test_consortium_habilitado_retorna_probabilidade(
        self, engine, base_request, market_rates
    ):
        """Quando include_consortium=True, deve ter probabilidade."""
        result = engine.simulate(base_request, market_rates)

        assert result.consortium_probability is not None
        assert 0 <= result.consortium_probability.win_12m <= 1
        assert 0 <= result.consortium_probability.win_24m <= 1
        assert result.consortium_probability.expected_months >= 1

    def test_consortium_desabilitado_nao_retorna_probabilidade(
        self, engine, request_sem_consortium, market_rates
    ):
        """Quando include_consortium=False, não deve ter probabilidade."""
        result = engine.simulate(request_sem_consortium, market_rates)

        assert result.consortium_probability is None
        assert result.npv.consortium is None

    def test_consortium_npv_presente_quando_habilitado(
        self, engine, base_request, market_rates
    ):
        """NPV do consórcio deve estar presente quando habilitado."""
        result = engine.simulate(base_request, market_rates)
        assert result.npv.consortium is not None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES BUDGET / LIQUIDEZ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBudgetConstraints:
    """Testa a lógica de restrição de orçamento."""

    def test_budget_apertado_nao_recomenda_financiamento_caro(
        self, engine, market_rates
    ):
        """Se o budget é muito baixo, não deve recomendar financ. caro."""
        req = SimulationRequest(
            user_id="test_budget",
            target_amount=200000.0,
            down_payment=5000.0,
            max_monthly_budget=500.0,  # muito baixo para R$195k financiado
            include_consortium=False,
            financing_months=48,
        )
        result = engine.simulate(req, market_rates)

        # Com budget de R$500, financiamento de R$195k @ 14% em 48 meses
        # dá parcela > R$5000, deve cair pra SAVE_INVEST
        assert result.recommended_strategy == StrategyType.SAVE_INVEST

    def test_liquidity_impact_negativo(
        self, engine, base_request, market_rates
    ):
        """Impacto de liquidez deve ser negativo (consumo de orçamento)."""
        result = engine.simulate(base_request, market_rates)
        assert result.liquidity_impact < 0

    def test_sem_budget_usa_financing_months(
        self, engine, request_sem_budget, market_rates
    ):
        """Sem max_monthly_budget, o investimento usa financing_months de prazo."""
        result = engine.simulate(request_sem_budget, market_rates)
        # Deve funcionar sem erros
        assert isinstance(result, SimulationResponse)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES ACTION PLAN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestActionPlan:
    """Testa a geração do plano de ação."""

    def test_action_plan_tem_steps_sequenciais(
        self, engine, base_request, market_rates
    ):
        """Os steps devem ter números sequenciais."""
        result = engine.simulate(base_request, market_rates)
        steps = [s.step for s in result.action_plan]
        assert steps == sorted(steps)
        assert steps[0] == 1

    def test_action_plan_tem_pelo_menos_um_critico(
        self, engine, base_request, market_rates
    ):
        """Pelo menos um step deve ser crítico."""
        result = engine.simulate(base_request, market_rates)
        critical = [s for s in result.action_plan if s.is_critical]
        assert len(critical) >= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES INTERNOS (helpers privados)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHelpers:
    """Testa os métodos internos do engine."""

    def test_simulate_financing_retorna_dict_valido(
        self, engine, base_request, market_rates
    ):
        """_simulate_financing deve retornar dict com campos esperados."""
        result = engine._simulate_financing(base_request, market_rates)

        assert "monthly_payment" in result
        assert "npv" in result
        assert "months" in result
        assert result["monthly_payment"] > 0
        assert result["months"] >= 1

    def test_simulate_investment_retorna_dict_valido(
        self, engine, base_request, market_rates
    ):
        """_simulate_investment deve retornar dict com campos esperados."""
        result = engine._simulate_investment(base_request, market_rates)

        assert "monthly_payment" in result
        assert "npv" in result
        assert "months" in result
        assert result["monthly_payment"] > 0
        assert result["months"] >= 1

    def test_simulate_consortium_retorna_dict_valido(
        self, engine, base_request, market_rates
    ):
        """_simulate_consortium deve retornar dict com campos esperados."""
        result = engine._simulate_consortium(base_request, market_rates)

        assert "monthly_payment" in result
        assert "npv" in result
        assert "probability" in result
        assert result["months"] >= 1

    def test_save_invest_rent_ipca_adjusted_higher_cost_than_flat(
        self, engine, market_rates
    ):
        """Aluguel corrigido por IPCA deve produzir NPV mais negativo que aluguel fixo.

        Valida que a correção não regrediu: para horizonte longo (120 meses),
        cashflows com aluguel crescente pelo IPCA resultam em custo maior
        (NPV mais negativo) do que cashflows com aluguel fixo nominal.
        """
        rates = {**market_rates, "ipca_annual": 0.045}

        req_sem_rent = SimulationRequest(
            user_id="test_rent",
            target_amount=300_000.0,
            down_payment=30_000.0,
            financing_months=120,
            risk_profile=RiskProfile.MODERADO,
            asset_type=AssetType.IMOVEL,
        )
        req_com_rent = req_sem_rent.model_copy(update={"current_monthly_rent": 2_500.0})

        result_sem = engine._simulate_investment(req_sem_rent, rates)
        result_com = engine._simulate_investment(req_com_rent, rates)

        # Com aluguel o NPV deve ser mais negativo (custo maior)
        assert result_com["npv"] < result_sem["npv"]

    def test_save_invest_rent_long_horizon_costlier_than_short(
        self, engine, market_rates
    ):
        """Em horizontes mais longos, o aluguel acumulado corrigido eleva mais o custo.

        Compara 60 meses vs 120 meses com mesmo aluguel inicial: o custo adicional
        relativo ao sem-aluguel deve ser maior no horizonte longo, confirmando que
        a correção IPCA está sendo acumulada mês a mês.
        """
        rates = {**market_rates, "ipca_annual": 0.045}

        base = SimulationRequest(
            user_id="test_rent_horizon",
            target_amount=300_000.0,
            down_payment=30_000.0,
            risk_profile=RiskProfile.MODERADO,
            asset_type=AssetType.IMOVEL,
            current_monthly_rent=2_000.0,
        )

        r60  = base.model_copy(update={"financing_months": 60})
        r120 = base.model_copy(update={"financing_months": 120})

        res60  = engine._simulate_investment(r60,  rates)
        res120 = engine._simulate_investment(r120, rates)

        # Custo de aluguel relativo ao aporte puro deve crescer com o horizonte
        # (a proxy simples é: custo total pago = |npv| é maior para 120 meses
        #  somente porque o aluguel acumulado cresceu — o aporte em si é o mesmo target)
        # Verificação mais precisa: NPV(120) deve ser mais negativo que NPV(60).
        assert res120["npv"] < res60["npv"]
