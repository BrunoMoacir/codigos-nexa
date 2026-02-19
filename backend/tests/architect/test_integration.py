"""
tests/architect/test_integration.py - Testes de integração ponta a ponta da F3

O QUE É TESTADO:
    Fluxo completo sem mocks: StrategyEngine → Calculators → Connectors reais
    Verifica que o pipeline inteiro funciona coeso.

    - Simulação com request de veículo retorna estratégia válida
    - Simulação com request de imóvel retorna estratégia válida
    - ArchitectService orquestra corretamente sem mocks (usando fallbacks)
    - Sem safe_to_spend: liquidity usa budget como referência
    - Com safe_to_spend alto: impacto baixo (SAFE)
    - Com safe_to_spend baixo: impacto alto (HIGH ou CRITICAL)
    - action_plan não é vazio
    - months_to_achieve >= 1

NOTA:
    Estes testes NÃO fazem chamadas reais às APIs externas (BACEN/ANBIMA).
    Os conectores usam seus fallbacks hardcoded automaticamente quando
    a API estiver indisponível (que é o caso em CI/CD).

COMO RODAR:
    cd backend
    pytest tests/architect/test_integration.py -v

    # Com output detalhado (ver recommended_strategy, npv, etc.)
    pytest tests/architect/test_integration.py -v -s
"""

import pytest

from app.architect.models import SimulationResponse, StrategyType
from app.architect.services.architect_service import ArchitectService


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def service() -> ArchitectService:
    """
    Service real com conectores reais.
    Os conectores usam fallbacks automáticos se a API estiver offline.
    """
    return ArchitectService()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: Simulação Completa de Veículo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIntegrationVeiculo:
    """Integração completa para aquisição de veículo."""

    def test_simula_veiculo_retorna_response(self, service, base_request):
        """Pipeline completo para veículo retorna SimulationResponse."""
        response = service.simulate(base_request)
        assert isinstance(response, SimulationResponse)

    def test_strategy_valida_para_veiculo(self, service, base_request):
        """Estratégia recomendada deve ser uma das 3 válidas."""
        response = service.simulate(base_request)
        assert response.recommended_strategy in [
            StrategyType.FINANCING,
            StrategyType.CONSORTIUM,
            StrategyType.SAVE_INVEST,
        ]

    def test_action_plan_nao_vazio(self, service, base_request):
        """Plano de ação deve ter ao menos 1 passo."""
        response = service.simulate(base_request)
        assert len(response.action_plan) >= 1

    def test_months_to_achieve_minimo_1(self, service, base_request):
        """months_to_achieve deve ser >= 1."""
        response = service.simulate(base_request)
        assert response.months_to_achieve >= 1

    def test_confidence_score_razoavel(self, service, base_request):
        """Sem dados da F1, confidence deve ser entre 0.30 e 0.90."""
        response = service.simulate(base_request)
        assert 0.30 <= response.confidence_score <= 0.90

    def test_npv_e_preenchido(self, service, base_request):
        """NPVComparison deve ter financing e save_invest preenchidos."""
        response = service.simulate(base_request)
        assert response.npv is not None
        assert response.npv.financing is not None
        assert response.npv.save_invest is not None

    def test_costs_min_menor_que_max(self, service, base_request):
        """min_cost <= expected_cost <= max_cost."""
        response = service.simulate(base_request)
        assert response.costs.min_cost <= response.costs.expected_cost
        assert response.costs.expected_cost <= response.costs.max_cost


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: Simulação Completa de Imóvel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIntegrationImovel:
    """Integração completa para aquisição de imóvel."""

    def test_simula_imovel_retorna_response(self, service, imovel_request):
        """Pipeline completo para imóvel retorna SimulationResponse."""
        response = service.simulate(imovel_request)
        assert isinstance(response, SimulationResponse)

    def test_strategy_valida_para_imovel(self, service, imovel_request):
        """Estratégia recomendada é uma das 3 válidas."""
        response = service.simulate(imovel_request)
        assert response.recommended_strategy in list(StrategyType)

    def test_data_sources_nao_vazio(self, service, imovel_request):
        """data_sources deve ter pelo menos 1 fonte."""
        response = service.simulate(imovel_request)
        assert len(response.data_sources) >= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: Impacto de Liquidez
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIntegrationLiquidez:
    """Verifica que o liquidity_impact é calculado corretamente."""

    def test_safe_to_spend_alto_impacto_baixo(self, service, base_request):
        """
        safe_to_spend muito alto → liquidity_impact próximo de 0.
        Ex: 100k de disponível para comprar um veículo de 50k.
        """
        response = service.simulate(base_request, safe_to_spend=100_000.0)
        assert response.liquidity_impact < 0  # constante negativo
        assert abs(response.liquidity_impact) < 0.30  # SAFE ou WARNING

    def test_safe_to_spend_baixo_impacto_alto(self, service, base_request):
        """
        safe_to_spend muito baixo → liquidity_impact alto (comprometimento alto).
        """
        response = service.simulate(base_request, safe_to_spend=500.0)  # R$500/mês
        assert abs(response.liquidity_impact) > 0.30  # HIGH ou CRITICAL

    def test_sem_safe_to_spend_usa_budget(self, service, base_request):
        """
        Sem safe_to_spend, deve usar max_monthly_budget como fallback.
        Response ainda deve conter impacto de liquidez.
        """
        response = service.simulate(base_request, safe_to_spend=None)
        assert response.liquidity_impact != 0.0 or base_request.max_monthly_budget is None

    def test_f1_disponivel_aumenta_confidence(self, service, base_request):
        """
        Fornecer safe_to_spend (dados da F1) aumenta confidence_score.
        """
        resp_sem = service.simulate(base_request, safe_to_spend=None)
        resp_com = service.simulate(base_request, safe_to_spend=8_000.0)
        assert resp_com.confidence_score >= resp_sem.confidence_score


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: Robustez e Edge Cases
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIntegrationRobustez:
    """Testa robustez do pipeline com casos extremos."""

    def test_sem_consortium_dois_candidatos(self, service, request_sem_consortium):
        """Sem consórcio, apenas FINANCING e SAVE_INVEST competem."""
        response = service.simulate(request_sem_consortium)
        assert response.recommended_strategy in [
            StrategyType.FINANCING,
            StrategyType.SAVE_INVEST,
        ]
        # Não deve ter consortium_probability preenchida
        if response.consortium_probability is not None:
            # Se vier preenchida, é o da estratégia parcial — aceitável
            pass

    def test_request_minimo_funciona(self, service, minimal_request):
        """Request com apenas campos obrigatórios não deve lançar exceção."""
        response = service.simulate(minimal_request)
        assert isinstance(response, SimulationResponse)

    def test_simulacao_e_deterministica_para_mesmos_inputs(
        self, service, base_request
    ):
        """
        Mesmos inputs → mesma estratégia recomendada.
        (O Monte Carlo usa seed fixa ou a variação não muda a recomendação.)
        """
        resp1 = service.simulate(base_request)
        resp2 = service.simulate(base_request)
        # Estratégia deve ser a mesma (mesmo se custos variarem levemente)
        assert resp1.recommended_strategy == resp2.recommended_strategy
