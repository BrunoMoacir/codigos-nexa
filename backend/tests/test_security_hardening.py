"""
Testes do hardening de segurança (auditoria 2026-07-12):

  1. Webhook Pluggy: segredo em tempo constante + identidade server-side
  2. Refresh tokens: rotação, uso único, rejeição como credencial de API
  3. Security headers em toda resposta (CSP estrito vs. /docs relaxado)
  4. LGPD: mascaramento de PII no audit + export/eliminação do titular
"""

import uuid as _uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app

_client = TestClient(app)
BASE = "/api/v1"


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════

class _FakeRedis:
    """Redis mínimo para blacklist/marcadores nos testes."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def exists(self, key):
        return 1 if key in self.store else 0

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


def _register_and_login() -> dict:
    email = f"sec_{_uuid.uuid4().hex[:10]}@nexa.test"
    password = "SenhaSegura@123"
    reg = _client.post(f"{BASE}/auth/register", json={
        "email": email, "password": password, "full_name": "Sec Test",
    })
    assert reg.status_code in (200, 201), reg.text
    login = _client.post(f"{BASE}/auth/token", data={
        "username": email, "password": password,
    })
    assert login.status_code == 200, login.text
    body = login.json()
    return {
        "user_id": body["user_id"],
        "access": body["access_token"],
        "refresh": body["refresh_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


# ═════════════════════════════════════════════════════════════════════
# 1. WEBHOOK
# ═════════════════════════════════════════════════════════════════════

_WEBHOOK_PAYLOAD = {
    "event": "transaction.created",
    "connector": {"id": "201"},
    "item": {"id": "item_sec_test"},
    "results": [],
}


class TestWebhookSecurity:
    def test_dev_sem_secret_aceita_com_warning(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "")
        monkeypatch.setenv("APP_MODE", "dev")
        resp = _client.post(
            f"{BASE}/transactions/webhook?user_id=dev_user", json=_WEBHOOK_PAYLOAD
        )
        assert resp.status_code == 200   # results vazio → nada a processar

    def test_prod_sem_secret_fail_closed_503(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "")
        monkeypatch.setenv("APP_MODE", "prod")
        resp = _client.post(f"{BASE}/transactions/webhook", json=_WEBHOOK_PAYLOAD)
        assert resp.status_code == 503

    def test_token_errado_401(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "segredo-forte")
        resp = _client.post(
            f"{BASE}/transactions/webhook",
            json=_WEBHOOK_PAYLOAD,
            headers={"X-Webhook-Token": "chute"},
        )
        assert resp.status_code == 401

    def test_token_certo_header_passa(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "segredo-forte")
        monkeypatch.setenv("APP_MODE", "dev")
        resp = _client.post(
            f"{BASE}/transactions/webhook?user_id=dev_user",
            json=_WEBHOOK_PAYLOAD,
            headers={"X-Webhook-Token": "segredo-forte"},
        )
        assert resp.status_code == 200

    def test_token_certo_query_passa(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "segredo-forte")
        monkeypatch.setenv("APP_MODE", "dev")
        resp = _client.post(
            f"{BASE}/transactions/webhook?token=segredo-forte&user_id=dev_user",
            json=_WEBHOOK_PAYLOAD,
        )
        assert resp.status_code == 200

    def test_prod_item_nao_mapeado_404_e_ignora_query_user(self, monkeypatch):
        """Em prod, user_id da query é IGNORADO; item sem dono → 404."""
        from app.core.config import settings
        import app.forecast.router_transactions as rt

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "segredo-forte")
        monkeypatch.setenv("APP_MODE", "prod")
        monkeypatch.setattr(rt, "resolve_user_from_item", lambda item_id: None)

        resp = _client.post(
            f"{BASE}/transactions/webhook?user_id=vitima_qualquer",
            json=_WEBHOOK_PAYLOAD,
            headers={"X-Webhook-Token": "segredo-forte"},
        )
        assert resp.status_code == 404

    def test_item_mapeado_usa_dono_do_mapeamento(self, monkeypatch):
        from app.core.config import settings
        import app.forecast.router_transactions as rt

        monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "segredo-forte")
        monkeypatch.setenv("APP_MODE", "prod")
        monkeypatch.setattr(
            rt, "resolve_user_from_item", lambda item_id: "dono_real"
        )
        resp = _client.post(
            f"{BASE}/transactions/webhook?user_id=atacante",
            json=_WEBHOOK_PAYLOAD,
            headers={"X-Webhook-Token": "segredo-forte"},
        )
        assert resp.status_code == 200   # aceito — como dono_real, não atacante


# ═════════════════════════════════════════════════════════════════════
# 2. REFRESH TOKENS
# ═════════════════════════════════════════════════════════════════════

class TestRefreshTokens:
    @pytest.fixture(autouse=True)
    def _fake_redis(self, monkeypatch):
        """Blacklist funcional sem Redis real (rotação precisa dela)."""
        import app.core.cache as cache_module

        fake = _FakeRedis()
        monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
        yield fake

    def test_login_retorna_par_de_tokens(self):
        auth = _register_and_login()
        assert auth["access"] and auth["refresh"]
        assert auth["access"] != auth["refresh"]

    def test_refresh_emite_novo_par(self):
        auth = _register_and_login()
        resp = _client.post(f"{BASE}/auth/refresh", json={"refresh_token": auth["refresh"]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_token"] != auth["access"]
        assert body["refresh_token"] != auth["refresh"]
        assert body["user_id"] == auth["user_id"]

    def test_rotacao_refresh_usado_vale_uma_vez(self):
        auth = _register_and_login()
        first = _client.post(f"{BASE}/auth/refresh", json={"refresh_token": auth["refresh"]})
        assert first.status_code == 200
        # reuso do MESMO refresh → 401 (foi revogado na rotação)
        second = _client.post(f"{BASE}/auth/refresh", json={"refresh_token": auth["refresh"]})
        assert second.status_code == 401

    def test_refresh_nao_serve_como_credencial_de_api(self):
        auth = _register_and_login()
        resp = _client.get(
            f"{BASE}/goals/{auth['user_id']}",
            headers={"Authorization": f"Bearer {auth['refresh']}"},
        )
        assert resp.status_code == 401

    def test_access_nao_serve_como_refresh(self):
        auth = _register_and_login()
        resp = _client.post(f"{BASE}/auth/refresh", json={"refresh_token": auth["access"]})
        assert resp.status_code == 401

    def test_refresh_lixo_401(self):
        resp = _client.post(f"{BASE}/auth/refresh", json={"refresh_token": "nao-e-jwt"})
        assert resp.status_code == 401

    def test_access_expira_em_30_minutos(self):
        from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES

        assert ACCESS_TOKEN_EXPIRE_MINUTES == 30


# ═════════════════════════════════════════════════════════════════════
# 3. SECURITY HEADERS
# ═════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    def test_headers_presentes_em_resposta_da_api(self):
        resp = _client.get("/health")
        h = resp.headers
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "no-referrer"
        assert "geolocation=()" in h["Permissions-Policy"]
        assert h["Cross-Origin-Opener-Policy"] == "same-origin"
        assert h["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"

    def test_docs_recebe_csp_relaxado(self):
        resp = _client.get("/docs")
        csp = resp.headers["Content-Security-Policy"]
        assert "cdn.jsdelivr.net" in csp
        assert "frame-ancestors 'none'" in csp

    def test_hsts_ausente_em_dev(self):
        # APP_ENV=development nos testes — HSTS envenenaria localhost
        resp = _client.get("/health")
        assert "Strict-Transport-Security" not in resp.headers


# ═════════════════════════════════════════════════════════════════════
# 4. LGPD
# ═════════════════════════════════════════════════════════════════════

class TestAuditMasking:
    def test_mask_email_padrao(self):
        from app.core.audit import mask_email

        assert mask_email("gabriel@nexa.com") == "g*****l@nexa.com"

    def test_mask_email_curto(self):
        from app.core.audit import mask_email

        assert mask_email("ab@x.com") == "a*@x.com"

    def test_mask_entrada_invalida(self):
        from app.core.audit import mask_email

        assert mask_email("") == "***"
        assert mask_email("sem-arroba") == "***"

    def test_login_failure_loga_email_mascarado(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="nexa.audit"):
            _client.post(f"{BASE}/auth/token", data={
                "username": "naoexiste_lgpd@nexa.com", "password": "errada",
            })
        audit_lines = [r.message for r in caplog.records if "AUTH_LOGIN_FAILURE" in r.message]
        assert audit_lines, "evento de auditoria não gerado"
        # email em claro nunca aparece; domínio + inicial/final preservados
        assert "naoexiste_lgpd@nexa.com" not in audit_lines[-1]
        assert "n" in audit_lines[-1] and "d@nexa.com" in audit_lines[-1]
        assert "*" in audit_lines[-1]


class TestPrivacyRights:
    def test_export_exige_dono(self):
        a, b = _register_and_login(), _register_and_login()
        resp = _client.get(f"{BASE}/privacy/export/{b['user_id']}", headers=a["headers"])
        assert resp.status_code == 403

    def test_export_retorna_estrutura_lgpd(self):
        auth = _register_and_login()
        resp = _client.get(f"{BASE}/privacy/export/{auth['user_id']}", headers=auth["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == auth["user_id"]
        assert "data" in body and "generated_at" in body
        # Propriedade de segurança: se a tabela users vier no export
        # (depende do backend de persistência do ambiente), o hash de
        # senha NUNCA pode estar presente.
        for row in body["data"].get("users", []):
            assert "hashed_password" not in row

    def test_erase_exige_frase_de_confirmacao(self):
        auth = _register_and_login()
        resp = _client.request(
            "DELETE",
            f"{BASE}/privacy/erase/{auth['user_id']}",
            json={"confirm": "sim"},
            headers=auth["headers"],
        )
        assert resp.status_code == 422

    def test_erase_apaga_conta_e_invalida_token(self):
        auth = _register_and_login()
        resp = _client.request(
            "DELETE",
            f"{BASE}/privacy/erase/{auth['user_id']}",
            json={"confirm": "EXCLUIR MEUS DADOS"},
            headers=auth["headers"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rows_deleted"] >= 1          # ao menos a linha de users
        assert body["tables_purged"] >= 1

        # o token do titular morreu junto com a conta
        after = _client.get(
            f"{BASE}/privacy/export/{auth['user_id']}", headers=auth["headers"]
        )
        assert after.status_code == 401


# ═════════════════════════════════════════════════════════════════════
# 5. IDOR — endpoints que estavam SEM autenticação (achados na auditoria)
# ═════════════════════════════════════════════════════════════════════

class TestIDORRegression:
    """
    goals e subscriptions tinham endpoints '..._public' e '..._simple'
    documentados como 'sem autenticação' — qualquer um lia dados
    financeiros de qualquer user_id. Agora exigem require_owner.
    """

    def test_goals_list_exige_token(self):
        resp = _client.get(f"{BASE}/goals/qualquer_user")
        assert resp.status_code == 401

    def test_goals_simple_exige_token(self):
        resp = _client.get(f"{BASE}/goals/qualquer_user/simple")
        assert resp.status_code == 401

    def test_goals_list_bloqueia_outro_usuario(self):
        a, b = _register_and_login(), _register_and_login()
        resp = _client.get(f"{BASE}/goals/{b['user_id']}", headers=a["headers"])
        assert resp.status_code == 403

    def test_subscriptions_exige_token(self):
        resp = _client.get(f"{BASE}/subscriptions/qualquer_user")
        assert resp.status_code == 401

    def test_subscriptions_simple_exige_token(self):
        resp = _client.get(f"{BASE}/subscriptions/qualquer_user/simple")
        assert resp.status_code == 401

    def test_subscriptions_bloqueia_outro_usuario(self):
        a, b = _register_and_login(), _register_and_login()
        resp = _client.get(f"{BASE}/subscriptions/{b['user_id']}", headers=a["headers"])
        assert resp.status_code == 403
