# tests/mobile/test_app_nativo.py — o que o app nativo exige do backend:
# token de widget, push FCM e o fim do SSRF do Web Push.

import base64
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

BASE = "/api/v1"
SENHA = "SenhaForte@2026"


@pytest.fixture(scope="module")
def cliente():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _conta(cliente):
    email = f"mob_{uuid.uuid4().hex[:8]}@nexa.test"
    r = cliente.post(f"{BASE}/auth/register", json={"email": email, "password": SENHA, "accepted_terms": True})
    assert r.status_code == 201, r.text
    t = cliente.post(f"{BASE}/auth/token", data={"username": email, "password": SENHA})
    assert t.status_code == 200, t.text
    return r.json()["user_id"], {"Authorization": f"Bearer {t.json()['access_token']}"}


APARELHO = "aparelho-" + uuid.uuid4().hex[:12]


# ── token do widget ─────────────────────────────────────────────────────────

class TestTokenDoWidget:

    def test_emite_le_e_revoga(self, cliente):
        uid, auth = _conta(cliente)
        r = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        assert token.startswith("hwt_")

        lido = cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": token})
        assert lido.status_code == 200, lido.text
        assert {"daily", "status", "headline"} <= set(lido.json())
        assert lido.json()["status"] == "SEM_DADOS"  # conta nova, sem banco

        assert cliente.request("DELETE", f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO},
                               headers=auth).json()["revoked"] == 1
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": token}).status_code == 401

    def test_novo_token_do_mesmo_aparelho_invalida_o_anterior(self, cliente):
        uid, auth = _conta(cliente)
        t1 = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        t2 = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": t1}).status_code == 401
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": t2}).status_code == 200

    def test_rota_do_widget_nao_aceita_jwt_nem_token_inventado(self, cliente):
        _, auth = _conta(cliente)
        assert cliente.get(f"{BASE}/widget/margem", headers=auth).status_code == 401
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": "hwt_inventado"}).status_code == 401

    def test_token_do_widget_nao_abre_outras_rotas(self, cliente):
        uid, auth = _conta(cliente)
        token = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        r = cliente.get(f"{BASE}/transactions/{uid}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    def test_nao_emite_token_para_outra_conta(self, cliente):
        dono, _ = _conta(cliente)
        _, auth_outro = _conta(cliente)
        r = cliente.post(f"{BASE}/widget/token/{dono}", json={"device_id": APARELHO}, headers=auth_outro)
        assert r.status_code == 403

    def test_banco_guarda_so_o_hash(self, cliente):
        from app.core.database import SessionLocal
        from app.widget.models_orm import WidgetToken

        uid, auth = _conta(cliente)
        token = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        with SessionLocal() as db:
            row = db.query(WidgetToken).filter(WidgetToken.user_id == uid).first()
        assert row.token_hash != token and len(row.token_hash) == 64

    def test_sair_de_todos_os_aparelhos_revoga_widget_e_push(self, cliente):
        uid, auth = _conta(cliente)
        token = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        fcm = "fcm_" + uuid.uuid4().hex * 2
        cliente.post(f"{BASE}/push/devices/{uid}", json={"token": fcm, "platform": "android"}, headers=auth)
        assert cliente.post(f"{BASE}/auth/logout-all", headers=auth).status_code in (200, 204)
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": token}).status_code == 401
        from app.core.notifications import fcm_sender

        assert fcm_sender.aparelhos_ativos(uid) == []

    def test_reset_de_senha_revoga_widget_e_push(self, cliente):
        # quem teve acesso passageiro à conta não pode guardar o widget e os
        # alertas depois que a vítima redefine a senha
        from app.core.account_tokens import PURPOSE_PASSWORD_RESET, issue_token
        from app.core.notifications import fcm_sender, push_sender

        uid, auth = _conta(cliente)
        token = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        fcm = "fcm_" + uuid.uuid4().hex * 2
        cliente.post(f"{BASE}/push/devices/{uid}", json={"token": fcm, "platform": "android"}, headers=auth)
        assert push_sender.save_subscription(uid, f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}", "p", "a")
        assert fcm_sender.aparelhos_ativos(uid)
        assert push_sender.get_active_subscriptions(uid)

        r = cliente.post(f"{BASE}/auth/reset-password", json={
            "token": issue_token(uid, PURPOSE_PASSWORD_RESET), "new_password": "OutraSenha@2026"})
        assert r.status_code == 200, r.text
        assert cliente.get(f"{BASE}/widget/margem", headers={"X-Widget-Token": token}).status_code == 401
        assert fcm_sender.aparelhos_ativos(uid) == []
        assert push_sender.get_active_subscriptions(uid) == []

    def test_token_anterior_ao_corte_de_sessao_nao_vale(self, cliente):
        # segunda trava: mesmo um caminho que corte as sessões e esqueça de
        # revogar o widget não deixa o token de 90 dias de pé
        import time

        from app.core.database import SessionLocal
        from app.core.db.users import encerrar_sessoes

        uid, auth = _conta(cliente)
        token = cliente.post(f"{BASE}/widget/token/{uid}", json={"device_id": APARELHO}, headers=auth).json()["token"]
        cabecalho = {"X-Widget-Token": token}
        assert cliente.get(f"{BASE}/widget/margem", headers=cabecalho).status_code != 401

        time.sleep(0.05)
        with SessionLocal() as db:
            assert encerrar_sessoes(db, uid)
        assert cliente.get(f"{BASE}/widget/margem", headers=cabecalho).status_code == 401


# ── aparelhos FCM ───────────────────────────────────────────────────────────

class TestAparelhos:

    def test_aparelho_troca_de_conta(self, cliente):
        from app.core.notifications import fcm_sender

        uid_a, auth_a = _conta(cliente)
        uid_b, auth_b = _conta(cliente)
        token = "fcm_" + uuid.uuid4().hex * 2
        assert cliente.post(f"{BASE}/push/devices/{uid_a}", json={"token": token, "platform": "ios"},
                            headers=auth_a).status_code == 200
        cliente.post(f"{BASE}/push/devices/{uid_b}", json={"token": token, "platform": "ios"}, headers=auth_b)
        assert fcm_sender.aparelhos_ativos(uid_a) == []
        assert [t for _, t in fcm_sender.aparelhos_ativos(uid_b)] == [token]

    def test_plataforma_e_token_validados(self, cliente):
        uid, auth = _conta(cliente)
        assert cliente.post(f"{BASE}/push/devices/{uid}", json={"token": "x" * 30, "platform": "windows"},
                            headers=auth).status_code == 422
        assert cliente.post(f"{BASE}/push/devices/{uid}", json={"token": "<script>" + "x" * 30, "platform": "ios"},
                            headers=auth).status_code == 422

    def test_nao_registra_aparelho_em_outra_conta(self, cliente):
        dono, _ = _conta(cliente)
        _, auth_outro = _conta(cliente)
        r = cliente.post(f"{BASE}/push/devices/{dono}", json={"token": "fcm_" + "y" * 40, "platform": "android"},
                         headers=auth_outro)
        assert r.status_code == 403


# ── SSRF do Web Push ────────────────────────────────────────────────────────

class TestEndpointDePush:

    @pytest.mark.parametrize("endpoint", [
        "http://169.254.169.254/latest/meta-data",
        "https://localhost/push",
        "https://api.interna.exemplo/push",
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com.atacante.com/x",
        "https://fcm.googleapis.com:8443/x",
    ])
    def test_recusa_endpoint_que_nao_e_servico_de_push(self, cliente, endpoint):
        uid, auth = _conta(cliente)
        r = cliente.post(f"{BASE}/push/subscribe/{uid}",
                         json={"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}, headers=auth)
        assert r.status_code == 422

    @pytest.mark.parametrize("endpoint", [
        "https://fcm.googleapis.com/fcm/send/abc123",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QWERTY",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
    ])
    def test_aceita_servicos_de_push_reais(self, endpoint):
        from app.core.notifications.push_sender import endpoint_permitido

        assert endpoint_permitido(endpoint)

    @pytest.mark.parametrize("endpoint", [
        # a stdlib lê o host depois do "@"; o urllib3 (que conecta) corta no "\"
        "https://evil.example\\@fcm.googleapis.com/fcm/send/abc",
        "https://10.0.0.5\\@fcm.googleapis.com/x",
        "https://10.0.0.5:8443\\@fcm.googleapis.com/x",
        "https://usuario:senha@fcm.googleapis.com/x",
        "https://fcm.googleapis.com@evil.example/x",
        "https://fcm.googleapis.com\t.evil.example/x",
        "https://fcm.googleapis.com /x",
        "https://fcm.googleapis.com:443:80/x",
        "https://fcm.googleapis.com／@evil.example/x",
        "https://fcm.googleapis.com./x",
    ])
    def test_recusa_url_ambigua_entre_parsers(self, endpoint):
        from app.core.notifications.push_sender import endpoint_permitido

        assert not endpoint_permitido(endpoint)

    def test_a_divergencia_entre_parsers_existe(self):
        # documenta por que a validação usa os dois parsers e recusa "\" e "@"
        from urllib.parse import urlparse

        from urllib3.util import parse_url

        url = "https://evil.example\\@fcm.googleapis.com/x"
        assert urlparse(url).hostname == "fcm.googleapis.com"
        assert parse_url(url).host == "evil.example"

    def test_sessao_do_envio_recusa_redirecionamento(self):
        # servidor local que responde 307: a sessão do envio não faz o 2º pedido
        import http.server
        import threading

        import requests

        from app.core.notifications.push_sender import _sessao_sem_redirecionamento

        pedidos = []

        class _Redireciona(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                pedidos.append(self.path)
                self.send_response(307)
                self.send_header("Location", "/interno")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        servidor = http.server.HTTPServer(("127.0.0.1", 0), _Redireciona)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        try:
            sessao = _sessao_sem_redirecionamento()
            with pytest.raises(requests.TooManyRedirects):
                sessao.post(f"http://127.0.0.1:{servidor.server_port}/push", data=b"x", timeout=5)
            assert pedidos == ["/push"]
        finally:
            servidor.shutdown()
            servidor.server_close()


# ── envio FCM (sem rede: MockTransport) ─────────────────────────────────────

def _conta_de_servico():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    dados = {"type": "service_account", "project_id": "hive-teste", "private_key": pem,
             "private_key_id": "kid1", "client_email": "fcm@hive-teste.iam.gserviceaccount.com"}
    return base64.b64encode(json.dumps(dados).encode()).decode()


class TestEnvioFcm:

    @pytest.fixture(autouse=True)
    def credencial(self, monkeypatch):
        from app.core.notifications import fcm_sender

        monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_B64", _conta_de_servico(), raising=False)
        fcm_sender._cache.update({"token": None, "expira": 0.0})

    def test_mensagem_privada_na_tela_de_bloqueio(self):
        from app.core.notifications.fcm_sender import montar_mensagem

        msg = montar_mensagem("tok", "Saldo negativo", "R$ 300 em 5 dias", "/feed", "saldo")["message"]
        assert msg["android"]["notification"]["visibility"] == "PRIVATE"
        assert all(isinstance(v, str) for v in msg["data"].values())

    def test_rota_externa_vira_feed(self):
        from app.core.notifications.fcm_sender import montar_mensagem

        assert montar_mensagem("t", "a", "b", "https://phishing.exemplo", "")["message"]["data"]["url"] == "/feed"

    def test_envia_e_marca_token_morto(self):
        from app.core.notifications import fcm_sender

        chamadas = []

        def servidor(req):
            chamadas.append(str(req.url))
            if "oauth2" in str(req.url):
                return httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
            if b'"token": "vivo"' in req.content or b'"token":"vivo"' in req.content:
                return httpx.Response(200, json={"name": "projects/hive-teste/messages/1"})
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND",
                                                       "details": [{"errorCode": "UNREGISTERED"}]}})

        transporte = httpx.MockTransport(servidor)
        assert fcm_sender.enviar("vivo", "t", "b", transport=transporte) == "ok"
        assert fcm_sender.enviar("morto", "t", "b", transport=transporte) == "invalido"
        assert sum("oauth2" in c for c in chamadas) == 1  # access token reaproveitado

    def test_credencial_invalida_desliga_o_canal(self, monkeypatch):
        from app.core.notifications import fcm_sender

        monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_B64", base64.b64encode(b'{"type":"user"}').decode(),
                            raising=False)
        assert fcm_sender.is_configured() is False
