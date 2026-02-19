"""
tests/architect/test_models.py - Testes dos Schemas Pydantic da F3

O QUE É TESTADO:
    - Criação válida de SimulationRequest com vários perfis
    - Validações de negócio: down_payment < target, target_date futuro
    - Propriedade calculada `principal`
    - Criação de SimulationResponse completo
    - Validações do CostScenario (min <= expected <= max)
    - Validações do ConsortiumProbability (probabilidades crescentes)

COMO RODAR:
    cd backend
    pytest tests/architect/test_models.py -v
"""

import pytest
from datetime import date, timedelta

from app.architect.models import (
    ActionStep,
    AmortizationMethod,
    AssetType,
    ConsortiumProbability,
    CostScenario,
    NPVComparison,
    RiskProfile,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: SimulationRequest
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSimulationRequest:
    """Testa criação, defaults e validações do request de entrada."""

    def test_criacao_minima_valida(self):
        """Request com apenas campos obrigatórios usa defaults corretos."""
        req = SimulationRequest(user_id="u1", target_amount=50_000.0)

        assert req.user_id == "u1"
        assert req.target_amount == 50_000.0
        # Defaults
        assert req.down_payment == 0.0
        assert req.max_monthly_budget is None
        assert req.risk_profile == RiskProfile.MODERADO
        assert req.include_consortium is True
        assert req.amortization_method == AmortizationMethod.PRICE

    def test_criacao_completa(self, base_request):
        """Request completo mantém todos os campos."""
        assert base_request.target_amount == 50_000.0
        assert base_request.down_payment == 10_000.0
        assert base_request.financing_months == 48

    def test_propriedade_principal(self):
        """principal = target_amount - down_payment."""
        req = SimulationRequest(
            user_id="u1",
            target_amount=100_000.0,
            down_payment=20_000.0,
        )
        assert req.principal == 80_000.0

    def test_principal_sem_entrada(self):
        """Sem entrada, principal == target_amount."""
        req = SimulationRequest(user_id="u1", target_amount=50_000.0)
        assert req.principal == 50_000.0

    def test_down_payment_nao_pode_ser_maior_que_target(self):
        """down_payment >= target_amount deve lançar ValidationError."""
        with pytest.raises(Exception):
            SimulationRequest(
                user_id="u1",
                target_amount=50_000.0,
                down_payment=60_000.0,  # maior que target
            )

    def test_down_payment_igual_ao_target_invalido(self):
        """down_payment == target_amount não é permitido."""
        with pytest.raises(Exception):
            SimulationRequest(
                user_id="u1",
                target_amount=50_000.0,
                down_payment=50_000.0,  # igual ao target
            )

    def test_target_date_no_passado_invalido(self):
        """target_date no passado deve lançar ValidationError."""
        with pytest.raises(Exception):
            SimulationRequest(
                user_id="u1",
                target_amount=50_000.0,
                target_date=date.today() - timedelta(days=1),
            )

    def test_target_date_hoje_invalido(self):
        """target_date = hoje não é permitido (deve ser futuro)."""
        with pytest.raises(Exception):
            SimulationRequest(
                user_id="u1",
                target_amount=50_000.0,
                target_date=date.today(),
            )

    def test_target_date_futuro_valido(self):
        """target_date no futuro deve ser aceito."""
        futuro = date.today() + timedelta(days=365)
        req = SimulationRequest(
            user_id="u1",
            target_amount=50_000.0,
            target_date=futuro,
        )
        assert req.target_date == futuro

    def test_target_amount_zero_invalido(self):
        """target_amount = 0 deve falhar."""
        with pytest.raises(Exception):
            SimulationRequest(user_id="u1", target_amount=0)

    def test_target_amount_negativo_invalido(self):
        """target_amount negativo deve falhar."""
        with pytest.raises(Exception):
            SimulationRequest(user_id="u1", target_amount=-1_000.0)

    def test_enums_sao_validos(self):
        """Todos os enums têm os valores esperados."""
        req = SimulationRequest(
            user_id="u1",
            target_amount=100_000.0,
            risk_profile=RiskProfile.AGRESSIVO,
            asset_type=AssetType.IMOVEL,
            amortization_method=AmortizationMethod.SAC,
        )
        assert req.risk_profile == RiskProfile.AGRESSIVO
        assert req.asset_type == AssetType.IMOVEL
        assert req.amortization_method == AmortizationMethod.SAC


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: CostScenario
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCostScenario:
    """Testa o modelo de cenário de custo (min <= expected <= max)."""

    def test_criacao_valida(self):
        """min <= expected <= max deve ser aceito."""
        cs = CostScenario(min_cost=90_000, expected_cost=100_000, max_cost=115_000)
        assert cs.min_cost == 90_000
        assert cs.expected_cost == 100_000
        assert cs.max_cost == 115_000

    def test_todos_iguais_valido(self):
        """min == expected == max é válido."""
        cs = CostScenario(min_cost=100_000, expected_cost=100_000, max_cost=100_000)
        assert cs.min_cost == cs.expected_cost == cs.max_cost

    def test_ordem_invalida_min_maior_que_expected(self):
        """min > expected deve lançar ValidationError."""
        with pytest.raises(Exception):
            CostScenario(min_cost=110_000, expected_cost=100_000, max_cost=120_000)

    def test_ordem_invalida_expected_maior_que_max(self):
        """expected > max deve lançar ValidationError."""
        with pytest.raises(Exception):
            CostScenario(min_cost=90_000, expected_cost=130_000, max_cost=120_000)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: ConsortiumProbability
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConsortiumProbability:
    """Testa que as probabilidades são crescentes (12m <= 24m <= 36m)."""

    def test_probabilidades_crescentes(self):
        """Probabilidades crescentes devem ser aceitas."""
        cp = ConsortiumProbability(
            win_12m=0.3, win_24m=0.6, win_36m=0.85,
            expected_months=20,
        )
        assert cp.win_12m < cp.win_24m < cp.win_36m

    def test_probabilidade_decrescente_invalida(self):
        """win_12m > win_24m deve falhar."""
        with pytest.raises(Exception):
            ConsortiumProbability(
                win_12m=0.7, win_24m=0.5, win_36m=0.9,
                expected_months=15,
            )

    def test_probabilidade_fora_de_0_a_1(self):
        """Valores fora de [0,1] devem falhar."""
        with pytest.raises(Exception):
            ConsortiumProbability(
                win_12m=1.2, win_24m=1.5, win_36m=1.8,
                expected_months=12,
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: ActionStep
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestActionStep:
    """Testa o modelo de passo do plano de ação."""

    def test_criacao_minima(self):
        """Step com campos obrigatórios funciona."""
        step = ActionStep(step=1, action="Reunir documentação")
        assert step.step == 1
        assert step.is_critical is False
        assert step.amount is None

    def test_criacao_completa(self):
        """Step com todos os campos."""
        step = ActionStep(
            step=2,
            action="Dar entrada de R$ 10.000",
            amount=10_000.0,
            is_critical=True,
        )
        assert step.amount == 10_000.0
        assert step.is_critical is True

    def test_step_zero_invalido(self):
        """step deve ser >= 1."""
        with pytest.raises(Exception):
            ActionStep(step=0, action="Ação")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: SimulationResponse
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSimulationResponse:
    """Testa criação e campos do response completo."""

    def _make_response(self, strategy=StrategyType.SAVE_INVEST):
        """Helper para criar um SimulationResponse válido."""
        return SimulationResponse(
            recommended_strategy=strategy,
            costs=CostScenario(
                min_cost=50_000, expected_cost=50_000, max_cost=50_000
            ),
            npv=NPVComparison(
                financing=-60_000.0,
                consortium=-55_000.0,
                save_invest=-50_000.0,
                discount_rate_used=0.0104,
            ),
            liquidity_impact=-0.20,
            months_to_achieve=36,
            action_plan=[
                ActionStep(step=1, action="Abrir conta em corretora", is_critical=True)
            ],
            confidence_score=0.85,
            data_sources=["bacen", "anbima"],
        )

    def test_criacao_valida(self):
        """SimulationResponse válido deve ser criado sem erros."""
        resp = self._make_response()
        assert resp.recommended_strategy == StrategyType.SAVE_INVEST
        assert resp.confidence_score == 0.85
        assert len(resp.action_plan) == 1

    def test_months_to_achieve_minimo_1(self):
        """months_to_achieve deve ser >= 1."""
        with pytest.raises(Exception):
            SimulationResponse(
                recommended_strategy=StrategyType.FINANCING,
                costs=CostScenario(min_cost=1, expected_cost=1, max_cost=1),
                npv=NPVComparison(
                    financing=-10.0, save_invest=-10.0, discount_rate_used=0.01
                ),
                liquidity_impact=0.0,
                months_to_achieve=0,  # inválido
                action_plan=[ActionStep(step=1, action="Ação")],
                confidence_score=0.5,
                data_sources=[],
            )

    def test_confidence_score_fora_de_0_a_1(self):
        """confidence_score deve estar em [0.0, 1.0]."""
        with pytest.raises(Exception):
            SimulationResponse(
                recommended_strategy=StrategyType.FINANCING,
                costs=CostScenario(min_cost=1, expected_cost=1, max_cost=1),
                npv=NPVComparison(
                    financing=-10.0, save_invest=-10.0, discount_rate_used=0.01
                ),
                liquidity_impact=0.0,
                months_to_achieve=1,
                action_plan=[ActionStep(step=1, action="Ação")],
                confidence_score=1.5,  # inválido
                data_sources=[],
            )

    def test_generated_at_e_preenchido_automaticamente(self):
        """generated_at é preenchido pelo factory datetime.now."""
        resp = self._make_response()
        assert resp.generated_at is not None

    def test_warnings_default_vazio(self):
        """warnings começa como lista vazia."""
        resp = self._make_response()
        assert resp.warnings == []

    def test_consortium_probability_opcional(self):
        """consortium_probability é None quando não calculado."""
        resp = self._make_response()
        assert resp.consortium_probability is None
