"""
tests/architect/test_service.py - Testes do ArchitectService (orquestrador da F3)

O QUE É TESTADO:
    - Fluxo principal: simulate() retorna SimulationResponse completo
    - Injeção de dependência: conectores mockados para isolamento
    - confidence_score cresce com dados da F1, cai com fallback
    - Dados da F1 (safe_to_spend) são propagados para liquidity_impact
    - InputValidator lançando ValueError para requests inválidos
    - Degradação graciosa: conector BACEN offline → warning no response
    - data_sources inclui "f1_safe_to_spend" quando disponível

COMO RODAR:
    cd backend
    pytest tests/architect/test_service.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from app.architect.models import SimulationRequest, SimulationResponse
from app.architect.services.architect_service import ArchitectService


class TestArchitectServiceSimulate:
    """Testa o fluxo completo do orquestrador."""

    def _make_service(self, bacen=None, anbima=None, market_rates=None, engine=None):
        """Helper que cria um service com conectores mockados."""
        return ArchitectService(
            bacen=bacen,
            anbima=anbima,
            market_rates=market_rates,
            engine=engine,
        )

    def test_simulate_retorna_simulation_response(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """Fluxo básico: retorna SimulationResponse sem exceção."""
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        response = service.simulate(base_request)

        assert isinstance(response, SimulationResponse)
        assert response.recommended_strategy is not None
        assert response.confidence_score >= 0.0

    def test_simulate_com_safe_to_spend_da_f1(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """Quando safe_to_spend é fornecido, data_sources inclui 'f1_safe_to_spend'."""
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        response = service.simulate(base_request, safe_to_spend=8_000.0)

        assert "f1_safe_to_spend" in response.data_sources

    def test_simulate_sem_f1_nao_inclui_f1_source(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """Sem safe_to_spend, data_sources NÃO deve ter 'f1_safe_to_spend'."""
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        response = service.simulate(base_request, safe_to_spend=None)

        assert "f1_safe_to_spend" not in response.data_sources

    def test_confidence_maior_com_f1(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """
        confidence_score com dados da F1 deve ser maior que sem dados da F1
        (regra: +0.10 para has_f1_data).
        """
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        resp_sem_f1 = service.simulate(base_request, safe_to_spend=None)
        resp_com_f1 = service.simulate(base_request, safe_to_spend=8_000.0)

        assert resp_com_f1.confidence_score >= resp_sem_f1.confidence_score

    def test_request_invalido_lanca_value_error(
        self, mock_bacen, mock_anbima, mock_market_rates
    ):
        """Request com violação de regra bloqueante → ValueError."""
        # Imóvel com valor abaixo do mínimo (R$30k < R$50k)
        from app.architect.models import AssetType
        req_invalido = SimulationRequest(
            user_id="u_inv",
            target_amount=30_000.0,
            down_payment=5_000.0,
            asset_type=AssetType.IMOVEL,  # mínimo R$50k
            max_monthly_budget=1_000.0,
        )
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)

        with pytest.raises(ValueError):
            service.simulate(req_invalido)

    def test_bacen_offline_adiciona_warning(
        self, base_request, mock_bacen_erro, mock_anbima, mock_market_rates
    ):
        """Quando BACEN está offline, response deve ter warning de fallback."""
        service = self._make_service(mock_bacen_erro, mock_anbima, mock_market_rates)
        response = service.simulate(base_request)

        # Deve ter retornado mesmo assim (degradação graciosa)
        assert isinstance(response, SimulationResponse)
        # E deve ter um warning mencionando BACEN ou fallback
        assert any("bacen" in w.lower() or "fallback" in w.lower() or "referência" in w.lower()
                   for w in response.warnings)

    def test_confidence_reduz_com_fallback(
        self, base_request, mock_bacen_erro, mock_anbima, mock_market_rates
    ):
        """Usar taxas de fallback reduz o confidence_score (-0.05)."""
        # Mock normal (sem erro)
        mock_bacen_ok = MagicMock()
        mock_bacen_ok.get_selic.return_value = 0.1325
        mock_bacen_ok.get_fallback_rates.return_value = {"selic_annual": 0.1325}

        service_ok = self._make_service(mock_bacen_ok, mock_anbima, mock_market_rates)
        service_fb = self._make_service(mock_bacen_erro, mock_anbima, mock_market_rates)

        resp_ok = service_ok.simulate(base_request)
        resp_fb = service_fb.simulate(base_request)

        # Com fallback, confidence deve ser <= confidence sem fallback
        assert resp_fb.confidence_score <= resp_ok.confidence_score

    def test_liquidity_impact_com_safe_to_spend(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """liquidity_impact deve refletir o safe_to_spend fornecido."""
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        # safe_to_spend muito alto → impact deve ser pequeno (SAFE)
        response = service.simulate(base_request, safe_to_spend=100_000.0)
        assert response.liquidity_impact < 0  # negativo
        assert abs(response.liquidity_impact) < 0.30  # abaixo de 30%

    def test_warnings_propagados_para_response(
        self, base_request, mock_bacen, mock_anbima, mock_market_rates
    ):
        """Avisos do InputValidator (ex: flags contraditórios) aparecem no response."""
        from app.architect.models import AssetType
        req_warning = SimulationRequest(
            user_id="test_warn",
            target_amount=30_000.0,
            down_payment=5_000.0,
            asset_type=AssetType.VEICULO,
            prefers_consortium=True,    # contradição:
            include_consortium=False,   # exclui mas prefere
            max_monthly_budget=1_500.0,
        )
        service = self._make_service(mock_bacen, mock_anbima, mock_market_rates)
        response = service.simulate(req_warning)

        # Response deve ter is_valid ainda = True mas com warnings
        assert isinstance(response, SimulationResponse)
        assert len(response.warnings) > 0


class TestComputeConfidence:
    """Testa a fórmula de cálculo do confidence_score."""

    def test_base_sem_ajustes(self):
        """Sem F1, sem fallback, 0 warnings → score = base."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=False,
            used_fallback_rates=False,
            warning_count=0,
        )
        assert abs(score - 0.85) < 0.001

    def test_f1_aumenta_0_10(self):
        """Com dados da F1, score aumenta 0.10."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=True,
            used_fallback_rates=False,
            warning_count=0,
        )
        assert abs(score - 0.95) < 0.001

    def test_fallback_reduz_0_05(self):
        """Com taxas de fallback, score reduz 0.05."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=False,
            used_fallback_rates=True,
            warning_count=0,
        )
        assert abs(score - 0.80) < 0.001

    def test_warning_reduz_0_02_cada(self):
        """3 warnings reduzem 3 * 0.02 = 0.06."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=False,
            used_fallback_rates=False,
            warning_count=3,
        )
        assert abs(score - 0.79) < 0.001

    def test_warnings_limitados_a_10(self):
        """Máx de penalidade por warnings = 0.10 (não importa quantos)."""
        score_5w = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=False,
            used_fallback_rates=False,
            warning_count=5,
        )
        score_100w = ArchitectService._compute_confidence(
            base_confidence=0.85,
            has_f1_data=False,
            used_fallback_rates=False,
            warning_count=100,
        )
        assert score_5w == score_100w  # ambos mínimo de 0.10 de penalidade

    def test_score_nao_vai_abaixo_de_0_30(self):
        """Score mínimo é 0.30."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.10,      # base muito baixa
            has_f1_data=False,
            used_fallback_rates=True,  # -0.05
            warning_count=100,         # -0.10 (cap)
        )
        assert score >= 0.30

    def test_score_nao_vai_acima_de_1_00(self):
        """Score máximo é 1.00."""
        score = ArchitectService._compute_confidence(
            base_confidence=0.95,      # base alta
            has_f1_data=True,          # +0.10 → tentaria 1.05
            used_fallback_rates=False,
            warning_count=0,
        )
        assert score <= 1.00
