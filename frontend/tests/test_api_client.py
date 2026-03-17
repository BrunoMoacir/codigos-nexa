# frontend/tests/test_api_client.py
# Suite de testes do NexaAPIClient — unitários (mock) + integração (backend real)
#
# Executar apenas unitários (sem backend):
#   cd frontend && python -m pytest tests/ -m unit -v
#
# Executar integração (docker-compose up -d obrigatório):
#   cd frontend && python -m pytest tests/ -m integration -v
#
# Executar tudo:
#   cd frontend && python -m pytest tests/ -v
#
# Credenciais de teste: golden_user_777 / password123

from __future__ import annotations

import sys
import os
import time
import unittest.mock as mock
from unittest.mock import MagicMock, patch, call

import pytest
import requests as requests_lib

# ─── Bootstrap: stub streamlit ANTES de qualquer import do módulo ────────────
# O Streamlit só existe dentro do contexto da app; fora disso criamos um mock
# completo para que os imports não quebrem.
_st_mock = MagicMock()
_st_mock.session_state = MagicMock()
_st_mock.session_state.__setitem__ = MagicMock()
_st_mock.session_state.__getitem__ = MagicMock(return_value=None)
_st_mock.session_state.get = MagicMock(return_value=None)
sys.modules["streamlit"] = _st_mock

# Adiciona /frontend ao path para imports relativos funcionarem
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.api import NexaAPIClient  # noqa: E402

# ─── Constantes ─────────────────────────────────────────────────────────────

BASE_URL     = "http://localhost:8000/api/v1"
TEST_USER    = "golden_user_777"
TEST_UID     = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"  # UUID retornado pelo backend
TEST_PASS    = "password123"
FAKE_TOKEN   = "eyJhbGciOiJIUzI1NiJ9.fake.signature"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 200, json_data=None, text: str = "") -> MagicMock:
    """Cria um objeto response mock com status, json e text configurados."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json = MagicMock(return_value=json_data if json_data is not None else {})
    return resp


def _mock_response_no_json(status_code: int, text: str = "text only") -> MagicMock:
    """Cria um response que explode ao chamar .json() (simula respostas não-JSON)."""
    resp = _mock_response(status_code, text=text)
    resp.json.side_effect = ValueError("No JSON object could be decoded")
    return resp


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def api() -> NexaAPIClient:
    """Cliente sem token — representa usuário não logado."""
    import streamlit as st
    st.session_state.get = MagicMock(return_value=None)
    return NexaAPIClient(base_url=BASE_URL)


@pytest.fixture
def api_logado() -> NexaAPIClient:
    """Cliente com token JWT injetado — representa sessão autenticada."""
    import streamlit as st
    st.session_state.get = MagicMock(
        side_effect=lambda key, default=None: FAKE_TOKEN if key == "jwt_token" else default
    )
    return NexaAPIClient(base_url=BASE_URL)


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 1: LOGIN
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLogin:

    # ── Happy path ───────────────────────────────────────────────────────

    def test_login_sucesso_retorna_success_true(self, api):
        payload = {"access_token": FAKE_TOKEN, "token_type": "bearer", "user_id": TEST_UID}
        with patch("utils.api.requests.post", return_value=_mock_response(200, payload)):
            result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is True

    def test_login_sucesso_inclui_user_id_no_retorno(self, api):
        """O frontend precisa do user_id UUID para enviar ao Chat."""
        payload = {"access_token": FAKE_TOKEN, "token_type": "bearer", "user_id": TEST_UID}
        with patch("utils.api.requests.post", return_value=_mock_response(200, payload)):
            result = api.login(TEST_USER, TEST_PASS)
        assert result.get("user_id") == TEST_UID

    def test_login_salva_token_na_sessao(self, api):
        payload = {"access_token": FAKE_TOKEN, "token_type": "bearer", "user_id": TEST_UID}
        import streamlit as st
        with patch("utils.api.requests.post", return_value=_mock_response(200, payload)):
            api.login(TEST_USER, TEST_PASS)
        st.session_state.__setitem__.assert_called()

    def test_login_token_salvo_e_o_access_token(self, api):
        payload = {"access_token": FAKE_TOKEN, "token_type": "bearer", "user_id": TEST_UID}
        saved = {}
        import streamlit as st
        st.session_state.__setitem__ = MagicMock(side_effect=lambda k, v: saved.update({k: v}))
        with patch("utils.api.requests.post", return_value=_mock_response(200, payload)):
            api.login(TEST_USER, TEST_PASS)
        assert saved.get("jwt_token") == FAKE_TOKEN

    # ── Erros do servidor ────────────────────────────────────────────────

    def test_login_401_retorna_success_false(self, api):
        body = {"detail": "Email ou senha incorretos"}
        with patch("utils.api.requests.post", return_value=_mock_response(401, body)):
            result = api.login(TEST_USER, "senha_errada")
        assert result["success"] is False

    def test_login_401_inclui_mensagem_de_erro(self, api):
        body = {"detail": "Email ou senha incorretos"}
        with patch("utils.api.requests.post", return_value=_mock_response(401, body)):
            result = api.login(TEST_USER, "senha_errada")
        assert "error" in result
        assert result["error"] != ""

    def test_login_500_retorna_success_false(self, api):
        with patch("utils.api.requests.post", return_value=_mock_response_no_json(500, "Internal error")):
            result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is False

    def test_login_resposta_sem_json_nao_explode(self, api):
        """Respostas não-JSON (HTML de erro do nginx, etc.) devem fazer fallback seguro."""
        with patch("utils.api.requests.post", return_value=_mock_response_no_json(503, "<html>down</html>")):
            result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is False
        assert result["error"] != ""

    # ── Contrato técnico da chamada HTTP ─────────────────────────────────

    def test_login_usa_endpoint_auth_token(self, api):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"access_token": FAKE_TOKEN, "user_id": TEST_UID})) as m:
            api.login(TEST_USER, TEST_PASS)
        call_url = m.call_args[0][0]
        assert "/auth/token" in call_url

    def test_login_envia_form_encoded_nao_json(self, api):
        """OAuth2 Password Flow exige `data=`, não `json=`."""
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"access_token": FAKE_TOKEN, "user_id": TEST_UID})) as m:
            api.login(TEST_USER, TEST_PASS)
        kw = m.call_args[1]
        assert "data" in kw, "Deve usar 'data=' para form-encoded"
        assert "json" not in kw, "Não deve usar 'json=' (quebraria o OAuth2)"

    def test_login_envia_username_e_password_no_form(self, api):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"access_token": FAKE_TOKEN, "user_id": TEST_UID})) as m:
            api.login("meu_usuario", "minha_senha")
        form = m.call_args[1]["data"]
        assert form["username"] == "meu_usuario"
        assert form["password"] == "minha_senha"

    def test_login_timeout_configurado(self, api):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"access_token": FAKE_TOKEN, "user_id": TEST_UID})) as m:
            api.login(TEST_USER, TEST_PASS)
        assert "timeout" in m.call_args[1], "Timeout não definido — pode travar a UI"

    # ── Exceções de rede ─────────────────────────────────────────────────

    def test_login_connection_error_retorna_success_false(self, api):
        with patch("utils.api.requests.post",
                   side_effect=requests_lib.exceptions.ConnectionError("refused")):
            result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is False

    def test_login_timeout_error_retorna_success_false(self, api):
        with patch("utils.api.requests.post",
                   side_effect=requests_lib.exceptions.Timeout("timed out")):
            result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is False

    def test_login_exception_generica_inclui_mensagem(self, api):
        with patch("utils.api.requests.post", side_effect=Exception("generic error")):
            result = api.login(TEST_USER, TEST_PASS)
        assert "generic error" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 2: HEADERS DE AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestHeaders:

    def test_sem_token_headers_vazios(self, api):
        headers = api._headers()
        assert "Authorization" not in headers

    def test_com_token_headers_tem_bearer(self, api_logado):
        headers = api_logado._headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_token_e_repassado_no_header(self, api_logado):
        headers = api_logado._headers()
        assert FAKE_TOKEN in headers["Authorization"]

    def test_get_requests_enviam_authorization(self, api_logado):
        for method_name in ["get_forecast_summary", "get_goals_summary"]:
            with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
                getattr(api_logado, method_name)(TEST_USER)
            headers = m.call_args[1].get("headers", {})
            assert "Authorization" in headers, f"{method_name} não enviou Authorization"

    def test_post_chat_envia_authorization(self, api_logado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message(TEST_USER, "oi")
        headers = m.call_args[1].get("headers", {})
        assert "Authorization" in headers


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 3: GET FORECAST SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGetForecastSummary:

    FORECAST_OK = {
        "financial_health": {
            "health_score": 88,
            "profile_type": "POUPADOR",
            "total_income": 31604.0,
            "burn_rate_alert": "NORMAL",
        },
        "safe_to_spend": {
            "safe_to_spend_total": 3955.81,
            "safe_to_spend_daily": 131.86,
            "risk_level": "LOW",
        },
    }

    def test_retorna_success_true_com_200(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.FORECAST_OK)):
            result = api_logado.get_forecast_summary(TEST_USER)
        assert result["success"] is True

    def test_retorna_data_completo(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.FORECAST_OK)):
            result = api_logado.get_forecast_summary(TEST_USER)
        assert result["data"] == self.FORECAST_OK

    def test_financial_health_tem_health_score(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.FORECAST_OK)):
            result = api_logado.get_forecast_summary(TEST_USER)
        assert "health_score" in result["data"]["financial_health"]

    def test_safe_to_spend_tem_valor_positivo(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.FORECAST_OK)):
            result = api_logado.get_forecast_summary(TEST_USER)
        sts = result["data"]["safe_to_spend"]
        assert sts["safe_to_spend_total"] >= 0

    def test_url_contem_user_id_e_forecast(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_forecast_summary("user_abc")
        url = m.call_args[0][0]
        assert "/forecast/" in url
        assert "user_abc" in url

    def test_retorna_404_como_success_false(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(404)):
            result = api_logado.get_forecast_summary("inexistente")
        assert result["success"] is False
        assert "404" in result["error"]

    def test_retorna_403_como_success_false(self, api_logado):
        """Token de outro usuário não pode acessar dados alheios."""
        body = {"detail": "Não autorizado"}
        with patch("utils.api.requests.get", return_value=_mock_response(403, body)):
            result = api_logado.get_forecast_summary("outro_user")
        assert result["success"] is False

    def test_exception_de_rede_retorna_success_false(self, api_logado):
        with patch("utils.api.requests.get",
                   side_effect=requests_lib.exceptions.ConnectionError("down")):
            result = api_logado.get_forecast_summary(TEST_USER)
        assert result["success"] is False

    def test_timeout_de_rede_retorna_success_false(self, api_logado):
        with patch("utils.api.requests.get",
                   side_effect=requests_lib.exceptions.Timeout("timeout")):
            result = api_logado.get_forecast_summary(TEST_USER)
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_timeout_configurado(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_forecast_summary(TEST_USER)
        assert "timeout" in m.call_args[1]


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 4: GET GOALS SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGetGoalsSummary:

    GOALS_OK = {
        "goals": [
            {
                "name": "Viagem para a Disney",
                "target_amount": 15000.0,
                "current_amount": 4500.0,
                "progress_pct": 30.0,
                "status": "ACTIVE",
                "projection": {"suggestion": "Poupe R$ 350/mês para atingir em 30 meses."},
            },
            {
                "name": "Reserva de Emergência",
                "target_amount": 20000.0,
                "current_amount": 18000.0,
                "progress_pct": 90.0,
                "status": "ACTIVE",
                "projection": {"suggestion": "Quase lá! Mais R$ 2.000 e você chega!"},
            },
        ],
        "total": 2,
    }

    def test_retorna_lista_de_metas(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.GOALS_OK)):
            result = api_logado.get_goals_summary(TEST_USER)
        assert result["success"] is True
        assert len(result["data"]["goals"]) == 2

    def test_cada_meta_tem_campos_obrigatorios(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.GOALS_OK)):
            result = api_logado.get_goals_summary(TEST_USER)
        for meta in result["data"]["goals"]:
            for campo in ("name", "target_amount", "current_amount", "progress_pct"):
                assert campo in meta, f"Campo '{campo}' ausente na meta"

    def test_progress_pct_entre_0_e_100(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.GOALS_OK)):
            result = api_logado.get_goals_summary(TEST_USER)
        for meta in result["data"]["goals"]:
            assert 0 <= meta["progress_pct"] <= 100, f"progress_pct fora do range: {meta['progress_pct']}"

    def test_current_amount_nao_maior_que_target(self, api_logado):
        """Nunca devemos ter current > target (indicaria bug no backend)."""
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.GOALS_OK)):
            result = api_logado.get_goals_summary(TEST_USER)
        for meta in result["data"]["goals"]:
            # Apenas verifica quando target > 0 (evita divisão por zero nos testes)
            if meta["target_amount"] > 0:
                assert meta["current_amount"] <= meta["target_amount"] * 1.01

    def test_projection_tem_suggestion_quando_presente(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.GOALS_OK)):
            result = api_logado.get_goals_summary(TEST_USER)
        for meta in result["data"]["goals"]:
            if meta.get("projection"):
                assert "suggestion" in meta["projection"]

    def test_url_contem_goals_e_user_id(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_goals_summary("user_teste")
        url = m.call_args[0][0]
        assert "/goals/" in url
        assert "user_teste" in url

    def test_lista_vazia_retorna_success_true(self, api_logado):
        """Usuário sem metas cadastradas ainda é sucesso — não erro."""
        with patch("utils.api.requests.get", return_value=_mock_response(200, {"goals": [], "total": 0})):
            result = api_logado.get_goals_summary(TEST_USER)
        assert result["success"] is True
        assert result["data"]["goals"] == []

    def test_erro_404_retorna_success_false(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(404)):
            result = api_logado.get_goals_summary("nao_existe")
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 5: GET BUDGET ADVICE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGetBudgetAdvice:

    BUDGET_OK = {
        "summary_text": "Essenciais: 35% (ideal 50%). Desejos: 16% (ideal 30%). Poupança: 0% (ideal 20%). Aumente a poupança para atingir as metas.",
        "group_summary": [
            {"group": "essenciais", "current_pct": 35.0, "target_pct": 50.0, "status": "OK"},
            {"group": "desejos",    "current_pct": 16.0, "target_pct": 30.0, "status": "OK"},
            {"group": "poupanca",   "current_pct":  0.0, "target_pct": 20.0, "status": "ATENÇÃO"},
        ],
        "actionable_cuts": [
            {"category": "lazer", "saving": 350.0, "reasoning": "Acima da média para seu perfil."},
        ],
        "rule_applied": "50/30/20 adaptado",
    }

    def test_retorna_summary_text(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.BUDGET_OK)):
            result = api_logado.get_budget_advice(TEST_USER, monthly_income=31604.0)
        assert result["success"] is True
        assert "summary_text" in result["data"]
        assert len(result["data"]["summary_text"]) > 10

    def test_group_summary_tem_3_grupos(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.BUDGET_OK)):
            result = api_logado.get_budget_advice(TEST_USER)
        grupos = {g["group"] for g in result["data"]["group_summary"]}
        assert grupos == {"essenciais", "desejos", "poupanca"}

    def test_cada_grupo_tem_current_e_target_pct(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.BUDGET_OK)):
            result = api_logado.get_budget_advice(TEST_USER)
        for grupo in result["data"]["group_summary"]:
            assert "current_pct" in grupo
            assert "target_pct" in grupo

    def test_actionable_cuts_lista_quando_presente(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.BUDGET_OK)):
            result = api_logado.get_budget_advice(TEST_USER)
        cuts = result["data"].get("actionable_cuts", [])
        assert isinstance(cuts, list)
        if cuts:
            assert "category" in cuts[0]
            assert "saving" in cuts[0]

    def test_url_contem_monthly_income_query_param(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_budget_advice(TEST_USER, monthly_income=5000.0)
        url = m.call_args[0][0]
        assert "monthly_income=5000" in url

    def test_url_contem_user_id_e_budget(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_budget_advice("user_x")
        url = m.call_args[0][0]
        assert "/budget/" in url
        assert "user_x" in url

    def test_monthly_income_default_presente_na_url(self, api_logado):
        """Chamada sem income explícito deve usar o default na URL."""
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_budget_advice(TEST_USER)
        url = m.call_args[0][0]
        assert "monthly_income=" in url

    def test_retorna_rule_applied_quando_presente(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, self.BUDGET_OK)):
            result = api_logado.get_budget_advice(TEST_USER)
        assert "rule_applied" in result["data"]

    def test_erro_500_retorna_success_false(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(500)):
            result = api_logado.get_budget_advice(TEST_USER)
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 6: POST CHAT MESSAGE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestPostChatMessage:

    CHAT_OK = {
        "response": "Seu safe to spend hoje é R$ 3.955,81. Isso corresponde a R$ 131,86 por dia.",
        "user_id": TEST_UID,
        "cost_usd": 0.00042,
        "tools_used": ["get_forecast_summary"],
    }

    def test_retorna_response_do_agente(self, api_logado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, self.CHAT_OK)):
            result = api_logado.post_chat_message(TEST_UID, "Qual meu safe to spend?")
        assert result["success"] is True
        assert "response" in result["data"]

    def test_resposta_nao_vazia(self, api_logado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, self.CHAT_OK)):
            result = api_logado.post_chat_message(TEST_UID, "msg")
        assert len(result["data"]["response"]) > 5

    def test_retorna_tools_used_quando_presente(self, api_logado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, self.CHAT_OK)):
            result = api_logado.post_chat_message(TEST_UID, "msg")
        assert isinstance(result["data"].get("tools_used", []), list)

    def test_retorna_cost_usd_quando_presente(self, api_logado):
        with patch("utils.api.requests.post", return_value=_mock_response(200, self.CHAT_OK)):
            result = api_logado.post_chat_message(TEST_UID, "msg")
        cost = result["data"].get("cost_usd")
        if cost is not None:
            assert cost >= 0

    def test_payload_json_tem_user_id_e_message(self, api_logado):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message("uid-abc", "Minha pergunta aqui")
        payload = m.call_args[1]["json"]
        assert payload["user_id"] == "uid-abc"
        assert payload["message"] == "Minha pergunta aqui"

    def test_nao_envia_form_encoded_usa_json(self, api_logado):
        """Chat usa JSON puro, não form-encoded."""
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message(TEST_UID, "msg")
        kw = m.call_args[1]
        assert "json" in kw
        assert "data" not in kw

    def test_timeout_pelo_menos_30s(self, api_logado):
        """LLM pode demorar — timeout mínimo de 30s é necessário."""
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message(TEST_UID, "msg")
        timeout = m.call_args[1].get("timeout", 0)
        assert timeout >= 30, f"Timeout muito curto: {timeout}s"

    def test_url_aponta_para_chat(self, api_logado):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message(TEST_UID, "oi")
        url = m.call_args[0][0]
        assert "/chat/" in url

    def test_erro_403_retorna_success_false_com_mensagem(self, api_logado):
        """Token de outro user_id deve causar 403 — frontend deve exibir erro claro."""
        body = {"detail": "Não autorizado (token não pertence a este user_id)"}
        with patch("utils.api.requests.post",
                   return_value=_mock_response(403, body, text=str(body))):
            result = api_logado.post_chat_message("outro_user", "msg")
        assert result["success"] is False
        assert "403" in result["error"]

    def test_erro_422_mensagem_invalida(self, api_logado):
        with patch("utils.api.requests.post",
                   return_value=_mock_response(422, text="Unprocessable")):
            result = api_logado.post_chat_message(TEST_UID, "")
        assert result["success"] is False
        assert "422" in result["error"]

    def test_timeout_de_rede_retorna_success_false(self, api_logado):
        with patch("utils.api.requests.post",
                   side_effect=requests_lib.exceptions.Timeout("LLM timeout")):
            result = api_logado.post_chat_message(TEST_UID, "msg")
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 7: CONSTRUÇÃO DE URL
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestUrlConstruction:

    def test_base_url_customizavel(self):
        client = NexaAPIClient(base_url="http://prod:8000/api/v1")
        assert client.base_url == "http://prod:8000/api/v1"

    def test_forecast_url_correta(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_forecast_summary("uid-123")
        assert m.call_args[0][0] == f"{BASE_URL}/forecast/uid-123"

    def test_goals_url_correta(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_goals_summary("uid-456")
        assert m.call_args[0][0] == f"{BASE_URL}/goals/uid-456"

    def test_budget_url_correta_com_income(self, api_logado):
        with patch("utils.api.requests.get", return_value=_mock_response(200, {})) as m:
            api_logado.get_budget_advice("uid-789", monthly_income=99999.0)
        url = m.call_args[0][0]
        assert url.startswith(f"{BASE_URL}/budget/uid-789")
        assert "monthly_income=99999" in url

    def test_chat_url_termina_com_barra(self, api_logado):
        """FastAPI roteia /chat/ diferente de /chat (sem barra)."""
        with patch("utils.api.requests.post",
                   return_value=_mock_response(200, {"response": "ok"})) as m:
            api_logado.post_chat_message("uid", "msg")
        url = m.call_args[0][0]
        assert url.endswith("/chat/")


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCO 8: INTEGRAÇÃO (backend real)
# ═══════════════════════════════════════════════════════════════════════════

def _backend_disponivel() -> bool:
    try:
        import requests as req
        r = req.get("http://localhost:8000/health", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


_skip_if_offline = pytest.mark.skipif(
    not _backend_disponivel(),
    reason="Backend offline. Rode: sudo docker-compose up -d",
)


@pytest.mark.integration
@_skip_if_offline
class TestIntegracaoLogin:

    def test_login_valido_retorna_success_true(self):
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login(TEST_USER, TEST_PASS)
        assert result["success"] is True

    def test_login_valido_retorna_user_id_uuid(self):
        """Backend deve retornar user_id (UUID) após login bem-sucedido."""
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login(TEST_USER, TEST_PASS)
        assert result.get("user_id") is not None
        assert len(result["user_id"]) > 8  # UUID mínimo

    def test_login_senha_invalida_retorna_false(self):
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login(TEST_USER, "senha_totalmente_errada_999")
        assert result["success"] is False

    def test_login_usuario_inexistente_retorna_false(self):
        import streamlit as st
        st.session_state.get = MagicMock(return_value=None)
        st.session_state.__setitem__ = MagicMock()

        api = NexaAPIClient()
        result = api.login("usuario_que_nao_existe_abc123", "qualquersenha")
        assert result["success"] is False


@pytest.mark.integration
@_skip_if_offline
class TestIntegracaoEndpoints:
    """Testes que chamam endpoints reais via backend Docker."""

    @pytest.fixture(autouse=True)
    def autenticar(self):
        import requests as req
        import streamlit as st

        resp = req.post(
            f"{BASE_URL}/auth/token",
            data={"username": TEST_USER, "password": TEST_PASS},
            timeout=5,
        )
        assert resp.status_code == 200, f"Falha ao autenticar: {resp.text}"
        data     = resp.json()
        token    = data["access_token"]
        real_uid = data.get("user_id", TEST_USER)

        st.session_state.get = MagicMock(
            side_effect=lambda k, d=None: token if k == "jwt_token" else d
        )
        self.api     = NexaAPIClient()
        self.real_uid = real_uid

    # ── Forecast ──────────────────────────────────────────────────────────

    def test_forecast_tem_financial_health(self):
        result = self.api.get_forecast_summary(self.real_uid)
        assert result["success"] is True
        assert "financial_health" in result["data"]

    def test_forecast_health_score_entre_0_e_100(self):
        result = self.api.get_forecast_summary(self.real_uid)
        score = result["data"]["financial_health"].get("health_score", 0)
        assert 0 <= score <= 100

    def test_forecast_safe_to_spend_nao_negativo(self):
        result = self.api.get_forecast_summary(self.real_uid)
        sts = result["data"].get("safe_to_spend", {})
        assert sts.get("safe_to_spend_total", 0) >= 0

    def test_forecast_tem_cashflow(self):
        result = self.api.get_forecast_summary(self.real_uid)
        assert "cashflow" in result["data"]

    def test_forecast_tem_shadow_invoices(self):
        result = self.api.get_forecast_summary(self.real_uid)
        assert "shadow_invoices" in result["data"]

    # ── Goals ─────────────────────────────────────────────────────────────

    def test_goals_retorna_lista(self):
        result = self.api.get_goals_summary(self.real_uid)
        assert result["success"] is True
        assert isinstance(result["data"].get("goals", []), list)

    def test_goals_campos_obrigatorios(self):
        result = self.api.get_goals_summary(self.real_uid)
        for meta in result["data"].get("goals", []):
            assert "name" in meta
            assert "target_amount" in meta
            assert "current_amount" in meta
            assert "progress_pct" in meta

    def test_goals_progress_pct_valido(self):
        result = self.api.get_goals_summary(self.real_uid)
        for meta in result["data"].get("goals", []):
            assert 0.0 <= meta["progress_pct"] <= 100.0

    # ── Budget ────────────────────────────────────────────────────────────

    def test_budget_tem_summary_text(self):
        result = self.api.get_budget_advice(self.real_uid, monthly_income=31604.0)
        assert result["success"] is True
        assert len(result["data"].get("summary_text", "")) > 10

    def test_budget_tem_3_grupos(self):
        result = self.api.get_budget_advice(self.real_uid, monthly_income=31604.0)
        grupos = {g["group"] for g in result["data"].get("group_summary", [])}
        assert grupos == {"essenciais", "desejos", "poupanca"}

    def test_budget_percentuais_razoaveis(self):
        result = self.api.get_budget_advice(self.real_uid, monthly_income=31604.0)
        total_pct = sum(
            g.get("current_pct", 0) for g in result["data"].get("group_summary", [])
        )
        assert 0 < total_pct < 200  # a soma real de %s gasto/renda

    # ── Chat ──────────────────────────────────────────────────────────────

    def test_chat_responde_pergunta_simples(self):
        result = self.api.post_chat_message(self.real_uid, "Qual meu safe to spend hoje?")
        assert result["success"] is True
        assert len(result["data"].get("response", "")) > 5

    def test_chat_resposta_tem_string(self):
        result = self.api.post_chat_message(self.real_uid, "Olá!")
        response = result["data"].get("response", "")
        assert isinstance(response, str)

    def test_chat_user_correto_nao_da_403(self):
        """Usar o user_id do token (não o username) deve evitar o 403."""
        result = self.api.post_chat_message(self.real_uid, "ping")
        # 403 indicaria bug na sincronia username vs user_id
        assert result.get("success") is not False or "403" not in result.get("error", "")
