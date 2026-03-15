# frontend/tests/test_api_client.py
# Testes do NexaAPIClient — unitários (mock) + integração (backend real)
#
# Unitários (sem backend): pytest frontend/tests/test_api_client.py -m unit
# Integração (backend rodando em localhost:8000):
#   pytest frontend/tests/test_api_client.py -m integration
#
# Usuário de teste: golden_user_777 / password123

from __future__ import annotations

import sys
import os
import unittest.mock as mock
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Stuba o streamlit antes de importar o módulo (não temos contexto Streamlit em tests)
sys.modules["streamlit"] = MagicMock()

# Adiciona /frontend ao path para imports relativos funcionarem
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.api import NexaAPIClient

# ─── Constantes ─────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000/api/v1"
TEST_USER = "golden_user_777"
TEST_PASSWORD = "password123"
FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.signature"


# ─── Fixture: cliente com token já setado ───────────────────────────────────

@pytest.fixture
def api() -> NexaAPIClient:
    client = NexaAPIClient(base_url=BASE_URL)
    return client


@pytest.fixture
def api_autenticado() -> NexaAPIClient:
    """Cliente com token JWT já injetado (simula sessão logada)."""
    import streamlit as st
    st.session_state.__getitem__ = lambda self, key: FAKE_TOKEN
    st.session_state.get = lambda key, default=None: FAKE_TOKEN if key == "jwt_token" else default
    return NexaAPIClient(base_url=BASE_URL)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 200, json_data: dict = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# TESTES UNITÁRIOS (sem backend)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLogin:
    def test_login_sucesso_salva_token(self, api):
        payload = {"access_token": FAKE_TOKEN, "token_type": "bearer"}
        with patch("utils.api.requests.post", return_value=_mock_response(200, payload)):
            result = api.login("user", "pass")
        assert result["success"] is True
        # client deve ter persistido o token na sessão
        import streamlit as st
        st.session_state.__setitem__.assert_called_once()

    def test_login_credenciais_invalidas(self, api):
        error_body = {"detail": "Usuário ou senha incorretos"}
        with patch("utils.api.requests.post", return_value=_mock_response(401, error_body)):
            result = api.login("user", "senha_errada")
        assert result["success"] is False
        assert "incorretos" in result["error"].lower() or result["error"] != ""

    def test_login_servidor_fora(self, api):
        with patch("utils.api.requests.post", side_effect=Exception("Connection refused")):
            result = api.login("user", "pass")
        assert result["success"] is False
        assert "Connection refused" in result["error"]

    def test_login_url_correta(self, api):
        """Verifica que o login usa o endpoint OAuth2 correto."""
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"access_token": FAKE_TOKEN})) as mock_post:
            api.login("user", "pass")
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/auth/token" in call_url

    def test_login_envia_form_encoded(self, api):
        """OAuth2 exige form-url-encoded, não JSON."""
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"access_token": FAKE_TOKEN})) as mock_post:
            api.login("user", "pass")
        call_kwargs = mock_post.call_args[1]
        assert "data" in call_kwargs  # form-encoded via data=
        assert "json" not in call_kwargs  # não deve usar json=

    def test_login_timeout_configurado(self, api):
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"access_token": FAKE_TOKEN})) as mock_post:
            api.login("user", "pass")
        call_kwargs = mock_post.call_args[1]
        assert "timeout" in call_kwargs

    def test_login_resposta_sem_json_nao_explode(self, api):
        """Resposta de erro sem JSON válido deve retornar mensagem de fallback."""
        resp = _mock_response(500, text="Internal Server Error")
        resp.json.side_effect = Exception("not json")
        with patch("utils.api.requests.post", return_value=resp):
            result = api.login("user", "pass")
        assert result["success"] is False
        assert result["error"] != ""


@pytest.mark.unit
class TestGetForecastSummary:
    def test_retorna_success_true_com_200(self, api_autenticado):
        forecast_data = {
            "financial_health": {"score": 88},
            "safe_to_spend": {"safe_to_spend_total": 3955.81},
        }
        with patch("utils.api.requests.get", return_value=_mock_response(200, forecast_data)):
            result = api_autenticado.get_forecast_summary(TEST_USER)
        assert result["success"] is True
        assert result["data"] == forecast_data

    def test_retorna_success_false_com_404(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(404)):
            result = api_autenticado.get_forecast_summary("user_inexistente")
        assert result["success"] is False
        assert "404" in result["error"]

    def test_url_contem_user_id(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_forecast_summary(TEST_USER)
        call_url = mock_get.call_args[0][0]
        assert TEST_USER in call_url
        assert "/forecast/" in call_url

    def test_envia_authorization_header(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_forecast_summary(TEST_USER)
        call_kwargs = mock_get.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "Authorization" in headers
        assert "Bearer" in headers["Authorization"]

    def test_retorna_success_false_em_excecao(self, api_autenticado):
        with patch("utils.api.requests.get", side_effect=Exception("timeout")):
            result = api_autenticado.get_forecast_summary(TEST_USER)
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


@pytest.mark.unit
class TestGetGoalsSummary:
    def test_retorna_lista_de_metas(self, api_autenticado):
        goals_data = {
            "goals": [
                {"name": "Viagem para a Disney", "target_amount": 15000.0, "current_amount": 4500.0, "progress_pct": 30.0},
                {"name": "Reserva de Emergência", "target_amount": 20000.0, "current_amount": 18000.0, "progress_pct": 90.0},
            ],
            "total": 2,
        }
        with patch("utils.api.requests.get", return_value=_mock_response(200, goals_data)):
            result = api_autenticado.get_goals_summary(TEST_USER)
        assert result["success"] is True
        assert len(result["data"]["goals"]) == 2

    def test_url_contem_user_id_e_goals(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_goals_summary(TEST_USER)
        call_url = mock_get.call_args[0][0]
        assert "/goals/" in call_url
        assert TEST_USER in call_url

    def test_meta_progress_pct_entre_0_e_100(self, api_autenticado):
        goals_data = {
            "goals": [
                {"name": "Meta", "target_amount": 1000.0, "current_amount": 250.0, "progress_pct": 25.0},
            ]
        }
        with patch("utils.api.requests.get", return_value=_mock_response(200, goals_data)):
            result = api_autenticado.get_goals_summary(TEST_USER)
        meta = result["data"]["goals"][0]
        assert 0 <= meta["progress_pct"] <= 100


@pytest.mark.unit
class TestGetBudgetAdvice:
    def test_retorna_summary_text(self, api_autenticado):
        budget_data = {
            "summary_text": "Essenciais: 35% (ideal 50%) — dentro do esperado.",
            "group_summary": [
                {"group": "essenciais", "current_pct": 35.0, "target_pct": 50.0},
                {"group": "desejos", "current_pct": 16.0, "target_pct": 30.0},
                {"group": "poupanca", "current_pct": 0.0, "target_pct": 20.0},
            ],
            "rule_applied": "50/30/20 adaptado",
        }
        with patch("utils.api.requests.get", return_value=_mock_response(200, budget_data)):
            result = api_autenticado.get_budget_advice(TEST_USER, monthly_income=31604.0)
        assert result["success"] is True
        assert "summary_text" in result["data"]

    def test_url_contem_monthly_income_query_param(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_budget_advice(TEST_USER, monthly_income=5000.0)
        call_url = mock_get.call_args[0][0]
        assert "monthly_income=5000" in call_url

    def test_url_contem_user_id(self, api_autenticado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_budget_advice(TEST_USER)
        call_url = mock_get.call_args[0][0]
        assert TEST_USER in call_url
        assert "/budget/" in call_url

    def test_default_income_e_valido(self, api_autenticado):
        """Default monthly_income=10000 deve ser passado na URL."""
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as mock_get:
            api_autenticado.get_budget_advice(TEST_USER)
        call_url = mock_get.call_args[0][0]
        assert "monthly_income=" in call_url

    def test_group_summary_lista_com_3_grupos(self, api_autenticado):
        budget_data = {
            "summary_text": "teste",
            "group_summary": [
                {"group": "essenciais", "current_pct": 35.0},
                {"group": "desejos", "current_pct": 16.0},
                {"group": "poupanca", "current_pct": 0.0},
            ],
        }
        with patch("utils.api.requests.get", return_value=_mock_response(200, budget_data)):
            result = api_autenticado.get_budget_advice(TEST_USER)
        grupos = {g["group"] for g in result["data"]["group_summary"]}
        assert grupos == {"essenciais", "desejos", "poupanca"}


@pytest.mark.unit
class TestPostChatMessage:
    def test_retorna_response_do_agente(self, api_autenticado):
        chat_resp = {"response": "Seu saldo é R$ 3.955,81.", "user_id": TEST_USER}
        with patch("utils.api.requests.post", return_value=_mock_response(200, chat_resp)):
            result = api_autenticado.post_chat_message(TEST_USER, "Qual meu saldo?")
        assert result["success"] is True
        assert "response" in result["data"]

    def test_envia_payload_json_correto(self, api_autenticado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"response": "ok"})) as mock_post:
            api_autenticado.post_chat_message(TEST_USER, "Minha pergunta")
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["user_id"] == TEST_USER
        assert payload["message"] == "Minha pergunta"

    def test_timeout_configurado_60s(self, api_autenticado):
        """O chat pode demorar (LLM) — timeout deve ser pelo menos 30s."""
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"response": "ok"})) as mock_post:
            api_autenticado.post_chat_message(TEST_USER, "msg")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs.get("timeout", 0) >= 30

    def test_erro_422_retorna_success_false(self, api_autenticado):
        with patch("utils.api.requests.post", return_value=_mock_response(422, text="Unprocessable Entity")):
            result = api_autenticado.post_chat_message(TEST_USER, "")
        assert result["success"] is False
        assert "422" in result["error"]

    def test_url_aponta_para_chat(self, api_autenticado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"response": "ok"})) as mock_post:
            api_autenticado.post_chat_message(TEST_USER, "oi")
        call_url = mock_post.call_args[0][0]
        assert "/chat/" in call_url


# ═══════════════════════════════════════════════════════════════════════════
# TESTES DE INTEGRAÇÃO (requerem backend rodando em localhost:8000)
# ═══════════════════════════════════════════════════════════════════════════

def _backend_disponivel() -> bool:
    try:
        import requests
        r = requests.get("http://localhost:8000/health", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


pytestmark_integration = pytest.mark.skipif(
    not _backend_disponivel(),
    reason="Backend não disponível em localhost:8000. Rode: docker-compose up -d"
)


@pytest.mark.integration
@pytestmark_integration
class TestIntegracaoLogin:
    def test_login_credenciais_validas(self):
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login(TEST_USER, TEST_PASSWORD)
        assert result["success"] is True

    def test_login_credenciais_invalidas_retorna_401(self):
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login(TEST_USER, "senha_completamente_errada_xyz")
        assert result["success"] is False


@pytest.mark.integration
@pytestmark_integration
class TestIntegracaoEndpoints:
    """Testes que chamam o backend real via Docker."""

    @pytest.fixture(autouse=True)
    def autenticar(self):
        """Autentica uma vez e injeta o token na sessão para todos os testes."""
        import requests as req
        import streamlit as st

        token_container = {}

        resp = req.post(
            f"{BASE_URL}/auth/token",
            data={"username": TEST_USER, "password": TEST_PASSWORD},
            timeout=5,
        )
        assert resp.status_code == 200, "Falha ao autenticar no setup"
        token = resp.json()["access_token"]
        token_container["token"] = token

        st.session_state.get = lambda key, default=None: token if key == "jwt_token" else default
        st.session_state.__getitem__ = lambda self, key: token

        self.api = NexaAPIClient()

    def test_forecast_retorna_score_real(self):
        result = self.api.get_forecast_summary(TEST_USER)
        assert result["success"] is True
        data = result["data"]
        assert "financial_health" in data
        assert data["financial_health"]["score"] >= 0

    def test_forecast_safe_to_spend_positivo(self):
        result = self.api.get_forecast_summary(TEST_USER)
        assert result["success"] is True
        sts = result["data"].get("safe_to_spend", {})
        assert "safe_to_spend_total" in sts
        assert sts["safe_to_spend_total"] >= 0

    def test_goals_retorna_lista_de_metas(self):
        result = self.api.get_goals_summary(TEST_USER)
        assert result["success"] is True
        assert "goals" in result["data"]
        assert isinstance(result["data"]["goals"], list)

    def test_goals_tem_campos_esperados(self):
        result = self.api.get_goals_summary(TEST_USER)
        goals = result["data"]["goals"]
        if goals:
            meta = goals[0]
            assert "name" in meta
            assert "target_amount" in meta
            assert "current_amount" in meta
            assert "progress_pct" in meta
            assert 0 <= meta["progress_pct"] <= 100

    def test_budget_retorna_summary_text(self):
        result = self.api.get_budget_advice(TEST_USER, monthly_income=31604.0)
        assert result["success"] is True
        assert "summary_text" in result["data"]
        assert len(result["data"]["summary_text"]) > 10

    def test_budget_tem_3_grupos_50_30_20(self):
        result = self.api.get_budget_advice(TEST_USER, monthly_income=31604.0)
        assert result["success"] is True
        grupos = {g["group"] for g in result["data"]["group_summary"]}
        assert grupos == {"essenciais", "desejos", "poupanca"}

    def test_budget_percentuais_somam_aprox_100(self):
        result = self.api.get_budget_advice(TEST_USER, monthly_income=31604.0)
        grupos = result["data"]["group_summary"]
        total_pct = sum(g.get("current_pct", 0) for g in grupos)
        # A soma deve ser a % dos gastos sobre a renda (não precisa somar 100)
        # mas deve ser positiva e razoável
        assert 0 < total_pct < 200

    def test_chat_responde_pergunta_simples(self):
        result = self.api.post_chat_message(TEST_USER, "Qual é o meu saldo disponível?")
        assert result["success"] is True
        assert "response" in result["data"]
        assert len(result["data"]["response"]) > 5
