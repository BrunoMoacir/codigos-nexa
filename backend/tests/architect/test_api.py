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
    O patch correto é "app.architect.router._service.simulate"
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

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"

# Path do singleton de service no módulo de rotas
_PATCH_SIMULATE = "app.architect.router._service.simulate"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def app():
    """Cria a aplicação FastAPI em modo de teste."""
    from app.main import app as fastapi_app  # app/main.py (não na raiz)
    from app.core.security import get_current_user

    async def _test_current_user():
        return TEST_USER_ID

    fastapi_app.dependency_overrides[get_current_user] = _test_current_user
    yield fastapi_app
    fastapi_app.dependency_overrides.pop(get_current_user, None)


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
        "user_id": TEST_USER_ID,
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: GET /architect/simulations  (listagem de histórico)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Paths dos helpers de DB usados na rota (para patch isolado)
_PATCH_GET_USER_SIMULATIONS = (
    "app.architect.router.get_user_simulations"
)
_PATCH_GET_SIMULATION       = "app.architect.router.get_simulation"
_PATCH_GET_USER_METRICS     = "app.architect.router.get_user_metrics"
_PATCH_SAVE_SIMULATION      = "app.architect.router.save_simulation"

# Payload mínimo de SimulationSummary retornado pelo banco
_SUMMARY = {
    "id":                   "uuid-abc-123",
    "created_at":           "2026-02-20T10:00:00+00:00",
    "target_amount":        80_000.0,
    "asset_type":           "VEICULO",
    "recommended_strategy": "FINANCING",
    "confidence_score":     0.85,
    "liquidity_impact":     -0.15,
    "months_to_achieve":    48,
    "expected_cost":        95_000.0,
}


class TestListSimulationsEndpoint:
    """Testa GET /architect/simulations."""

    def test_retorna_200_com_lista(self, client):
        """Retorna 200 e lista quando o banco tem resultados."""
        with patch(_PATCH_GET_USER_SIMULATIONS, return_value=[_SUMMARY]):
            response = client.get(
                "/api/v1/architect/simulations", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_retorna_lista_vazia_para_usuario_novo(self, client):
        """Usuário sem histórico → retorna lista vazia, não 404."""
        with patch(_PATCH_GET_USER_SIMULATIONS, return_value=[]):
            response = client.get(
                "/api/v1/architect/simulations", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 200
        assert response.json() == []

    def test_campos_obrigatorios_presentes(self, client):
        """Cada item deve ter id, created_at, recommended_strategy e confidence_score."""
        with patch(_PATCH_GET_USER_SIMULATIONS, return_value=[_SUMMARY]):
            response = client.get(
                "/api/v1/architect/simulations", params={"user_id": TEST_USER_ID}
            )
        item = response.json()[0]
        for campo in ("id", "created_at", "recommended_strategy", "confidence_score"):
            assert campo in item, f"Campo '{campo}' ausente"

    def test_sem_user_id_retorna_422(self, client):
        """user_id é obrigatório → 422 sem ele."""
        response = client.get("/api/v1/architect/simulations")
        assert response.status_code == 422

    def test_limit_aceito_como_query_param(self, client):
        """limit deve ser aceito sem erro."""
        with patch(_PATCH_GET_USER_SIMULATIONS, return_value=[]):
            response = client.get(
                "/api/v1/architect/simulations",
                params={"user_id": TEST_USER_ID, "limit": 5},
            )
        assert response.status_code == 200

    def test_asset_type_filter_aceito(self, client):
        """asset_type deve ser aceito como query param sem erro."""
        with patch(_PATCH_GET_USER_SIMULATIONS, return_value=[]):
            response = client.get(
                "/api/v1/architect/simulations",
                params={"user_id": TEST_USER_ID, "asset_type": "IMOVEL"},
            )
        assert response.status_code == 200

    def test_erro_interno_retorna_500(self, client):
        """Exceção no banco → 500."""
        with patch(
            _PATCH_GET_USER_SIMULATIONS, side_effect=RuntimeError("DB error")
        ):
            response = client.get(
                "/api/v1/architect/simulations", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: GET /architect/simulations/{simulation_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Payload completo retornado pelo get_simulation (inclui request/response JSON)
_FULL_SIM = {
    **_SUMMARY,
    # o endpoint verifica o dono (sim["user_id"] == current_user) → precisa
    # bater com o override de get_current_user do fixture
    "user_id":            TEST_USER_ID,
    "amortization_type":  "PRICE",
    "financing_months":   48,
    "down_payment":       10_000.0,
    "max_monthly_budget": 2_000.0,
    "request":  {"user_id": TEST_USER_ID, "target_amount": 80_000.0},
    "response": {"recommended_strategy": "FINANCING"},
}


class TestGetSimulationByIdEndpoint:
    """Testa GET /architect/simulations/{simulation_id}."""

    def test_retorna_200_para_id_existente(self, client):
        """ID existente → 200."""
        with patch(_PATCH_GET_SIMULATION, return_value=_FULL_SIM):
            response = client.get(
                "/api/v1/architect/simulations/uuid-abc-123"
            )
        assert response.status_code == 200

    def test_retorna_payload_completo(self, client):
        """Response inclui campos indexáveis e os JSONs de request/response."""
        with patch(_PATCH_GET_SIMULATION, return_value=_FULL_SIM):
            response = client.get(
                "/api/v1/architect/simulations/uuid-abc-123"
            )
        data = response.json()
        assert "request" in data
        assert "response" in data
        assert data["id"] == "uuid-abc-123"

    def test_retorna_404_para_id_inexistente(self, client):
        """ID que não existe no banco → 404."""
        with patch(_PATCH_GET_SIMULATION, return_value=None):
            response = client.get(
                "/api/v1/architect/simulations/id-que-nao-existe"
            )
        assert response.status_code == 404

    def test_erro_interno_retorna_500(self, client):
        """Exceção no banco → 500."""
        with patch(
            _PATCH_GET_SIMULATION, side_effect=RuntimeError("DB error")
        ):
            response = client.get(
                "/api/v1/architect/simulations/qualquer-id"
            )
        assert response.status_code == 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: GET /architect/metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_METRICS = {
    "user_id":              "user_1",
    "total_simulations":    5,
    "last_simulated_at":    "2026-02-20T10:00:00+00:00",
    "first_simulated_at":   "2026-01-10T08:30:00+00:00",
    "favorite_strategy":    "FINANCING",
    "avg_confidence_score": 0.84,
}


class TestGetMetricsEndpoint:
    """Testa GET /architect/metrics."""

    def test_retorna_200_para_usuario_com_historico(self, client):
        """Usuário com simulações → 200."""
        with patch(_PATCH_GET_USER_METRICS, return_value=_METRICS):
            response = client.get(
                "/api/v1/architect/metrics", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 200

    def test_campos_obrigatorios_presentes(self, client):
        """Response deve ter user_id, total_simulations e favorite_strategy."""
        with patch(_PATCH_GET_USER_METRICS, return_value=_METRICS):
            response = client.get(
                "/api/v1/architect/metrics", params={"user_id": TEST_USER_ID}
            )
        data = response.json()
        assert data["user_id"] == "user_1"
        assert data["total_simulations"] == 5
        assert data["favorite_strategy"] == "FINANCING"

    def test_usuario_sem_simulacoes_recebe_zeros_e_nao_404(self, client):
        """Sem simulação é estado normal da tela → 200 com total 0 (era 404)."""
        with patch(_PATCH_GET_USER_METRICS, return_value=None):
            response = client.get(
                "/api/v1/architect/metrics", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total_simulations"] == 0
        assert data["favorite_strategy"] is None

    def test_sem_user_id_retorna_422(self, client):
        """user_id é obrigatório → 422."""
        response = client.get("/api/v1/architect/metrics")
        assert response.status_code == 422

    def test_erro_interno_retorna_500(self, client):
        """Exceção no banco → 500."""
        with patch(
            _PATCH_GET_USER_METRICS, side_effect=RuntimeError("DB error")
        ):
            response = client.get(
                "/api/v1/architect/metrics", params={"user_id": TEST_USER_ID}
            )
        assert response.status_code == 500
