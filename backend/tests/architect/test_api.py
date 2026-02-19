"""
tests/architect/test_api.py - Testes de endpoint da API REST (F3)

O QUE É TESTADO:
    POST /architect/simulate:
        - Retorna 200 com SimulationResponse válido
        - Retorna 422 para request com dados inválidos (Pydantic)
        - Retorna 422 para violações de regras de negócio (ValueError do service)
        - Retorna 500 para erro interno inesperado

    GET /architect/health:
        - Retorna 200 com JSON {"status": "ok", "module": "architect", "timestamp": ...}

ESTRATÉGIA:
    Usa TestClient do FastAPI (sem servidor HTTP real).
    O _service (singleton) é patcheado para isolar a API da lógica de negócio.
    O patch correto é "app.api.v1.routes.architect._service.simulate"
    pois _service = ArchitectService() é instanciado no módulo de rotas.

COMO RODAR:
    cd backend
    pytest tests/architect/test_api.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.architect.models import (
    ActionStep,
    CostScenario,
    NPVComparison,
    SimulationResponse,
    StrategyType,
)

# Path do singleton de service no módulo de rotas
_PATCH_SIMULATE = "app.api.v1.routes.architect._service.simulate"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def app():
    """Cria a aplicação FastAPI em modo de teste."""
    from app.main import app as fastapi_app  # app/main.py (não na raiz)
    return fastapi_app


@pytest.fixture
def client(app):
    """TestClient para fazer requisições sem servidor HTTP real."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_response() -> SimulationResponse:
    """SimulationResponse predefinido para mockar o service."""
    return SimulationResponse(
        recommended_strategy=StrategyType.SAVE_INVEST,
        costs=CostScenario(
            min_cost=45_000, expected_cost=50_000, max_cost=58_000
        ),
        npv=NPVComparison(
            financing=-62_000.0,
            consortium=-57_000.0,
            save_invest=-50_000.0,
            discount_rate_used=0.0104,
        ),
        liquidity_impact=-0.18,
        months_to_achieve=36,
        action_plan=[
            ActionStep(step=1, action="Abrir conta em investimentos", is_critical=True),
            ActionStep(step=2, action="Aplicar R$ 1.100/mês em CDB"),
        ],
        confidence_score=0.87,
        data_sources=["bacen", "anbima", "market_rates"],
    )


@pytest.fixture
def valid_payload() -> dict:
    """Payload JSON válido para POST /architect/simulate."""
    return {
        "user_id": "test_api_user",
        "target_amount": 50000.0,
        "down_payment": 10000.0,
        "max_monthly_budget": 2000.0,
        "risk_profile": "moderado",
        "asset_type": "VEICULO",
        "financing_months": 48,
        "amortization_method": "PRICE",
        "include_consortium": True,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: Health Check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHealthEndpoint:
    """Testa GET /architect/health."""

    def test_health_retorna_200(self, client):
        """Health check deve retornar HTTP 200."""
        response = client.get("/api/v1/architect/health")
        assert response.status_code == 200

    def test_health_retorna_status_ok(self, client):
        """Body deve ter {"status": "ok"}."""
        response = client.get("/api/v1/architect/health")
        data = response.json()
        assert data.get("status") == "ok"

    def test_health_retorna_module_architect(self, client):
        """Body deve identificar o módulo como 'architect'."""
        response = client.get("/api/v1/architect/health")
        data = response.json()
        assert data.get("module") == "architect"

    def test_health_retorna_timestamp(self, client):
        """Body deve conter campo 'timestamp'."""
        response = client.get("/api/v1/architect/health")
        data = response.json()
        assert "timestamp" in data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: POST /architect/simulate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSimulateEndpoint:
    """Testa POST /architect/simulate."""

    def test_simulate_retorna_200_com_payload_valido(
        self, client, valid_payload, mock_response
    ):
        """Payload válido deve retornar HTTP 200."""
        with patch(_PATCH_SIMULATE, return_value=mock_response):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        assert response.status_code == 200

    def test_simulate_retorna_recommended_strategy(
        self, client, valid_payload, mock_response
    ):
        """Response deve ter recommended_strategy."""
        with patch(_PATCH_SIMULATE, return_value=mock_response):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        data = response.json()
        assert "recommended_strategy" in data

    def test_simulate_retorna_action_plan(
        self, client, valid_payload, mock_response
    ):
        """Response deve incluir action_plan com pelo menos 1 step."""
        with patch(_PATCH_SIMULATE, return_value=mock_response):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        data = response.json()
        assert "action_plan" in data
        assert len(data["action_plan"]) >= 1

    def test_simulate_retorna_npv(
        self, client, valid_payload, mock_response
    ):
        """Response deve ter objeto npv."""
        with patch(_PATCH_SIMULATE, return_value=mock_response):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        data = response.json()
        assert "npv" in data

    def test_simulate_retorna_422_para_target_negativo(self, client):
        """target_amount negativo → 422 (Pydantic valida antes do service)."""
        payload = {"user_id": "u1", "target_amount": -1000.0}
        response = client.post("/api/v1/architect/simulate", json=payload)
        assert response.status_code == 422

    def test_simulate_retorna_422_sem_user_id(self, client):
        """Sem user_id → 422 (campo obrigatório)."""
        payload = {"target_amount": 50000.0}
        response = client.post("/api/v1/architect/simulate", json=payload)
        assert response.status_code == 422

    def test_simulate_retorna_422_para_violacao_negocio(
        self, client, valid_payload
    ):
        """ValueError do service deve resultar em HTTP 422."""
        with patch(
            _PATCH_SIMULATE,
            side_effect=ValueError("Principal abaixo do mínimo"),
        ):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        assert response.status_code == 422

    def test_simulate_retorna_500_para_erro_interno(
        self, client, valid_payload
    ):
        """Exception inesperada deve resultar em HTTP 500."""
        with patch(
            _PATCH_SIMULATE,
            side_effect=RuntimeError("Erro interno inesperado"),
        ):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        assert response.status_code == 500

    def test_simulate_retorna_confidence_score(
        self, client, valid_payload, mock_response
    ):
        """Response deve ter confidence_score entre 0 e 1."""
        with patch(_PATCH_SIMULATE, return_value=mock_response):
            response = client.post("/api/v1/architect/simulate", json=valid_payload)
        data = response.json()
        assert "confidence_score" in data
        assert 0.0 <= data["confidence_score"] <= 1.0
