"""
Testes do canal Web Push (PWA, R1.d):
  - endpoints de inscrição (/push/*)
  - escalonamento automático de WARNING/CRITICAL para push no deliver()
  - revogação de inscrição morta (HTTP 410 do push service)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.notifications import push_sender
from app.core.notifications.delivery_service import deliver
from app.core.security import get_current_user, require_owner
from app.notifications.push_router import router as push_router

_USER = "test_user"

_app = FastAPI()
_app.include_router(push_router)
_app.dependency_overrides[get_current_user] = lambda: _USER
_app.dependency_overrides[require_owner] = lambda: _USER
_client = TestClient(_app)

_SUB_BODY = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
    "keys": {"p256dh": "chave-p256dh", "auth": "chave-auth"},
}


class TestPushEndpoints:
    def test_vapid_public_key_expoe_estado(self):
        resp = _client.get("/push/vapid-public-key")
        assert resp.status_code == 200
        body = resp.json()
        assert "configured" in body and "public_key" in body

    def test_subscribe_persiste_inscricao(self, monkeypatch):
        captured = {}

        def _fake_save(user_id, endpoint, p256dh, auth, user_agent=""):
            captured.update(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
            return True

        monkeypatch.setattr(push_sender, "save_subscription", _fake_save)
        resp = _client.post(f"/push/subscribe/{_USER}", json=_SUB_BODY)
        assert resp.status_code == 200
        assert captured["user_id"] == _USER
        assert captured["endpoint"] == _SUB_BODY["endpoint"]
        assert captured["p256dh"] == "chave-p256dh"

    def test_subscribe_endpoint_invalido_422(self):
        resp = _client.post(f"/push/subscribe/{_USER}", json={"endpoint": "x", "keys": {}})
        assert resp.status_code == 422

    def test_status(self, monkeypatch):
        monkeypatch.setattr(push_sender, "is_configured", lambda: True)
        monkeypatch.setattr(push_sender, "has_active_subscription", lambda uid: True)
        body = _client.get(f"/push/status/{_USER}").json()
        assert body == {"configured": True, "subscribed": True}


class TestDeliveryEscalation:
    @pytest.fixture(autouse=True)
    def _stub_delivery_side_effects(self, monkeypatch):
        import app.core.notifications.delivery_service as ds

        monkeypatch.setattr(ds, "_get_user_channels", lambda uid: ["in_app"])
        monkeypatch.setattr(ds, "_log_delivery", lambda *a, **k: None)

    def test_warning_escala_para_push_quando_inscrito(self, monkeypatch):
        sent = {}

        monkeypatch.setattr(push_sender, "is_configured", lambda: True)
        monkeypatch.setattr(push_sender, "has_active_subscription", lambda uid: True)

        def _fake_send(user_id, title, body, url="/", tag=""):
            sent.update(user_id=user_id, title=title, body=body, tag=tag)
            return 1, 0

        monkeypatch.setattr(push_sender, "send_to_user", _fake_send)

        results = deliver(
            user_id=_USER,
            subject="⚠️ Tarifa aumentou",
            html_body="<h2>Tarifa</h2><p>Subiu 20%</p>",
            notification_type="TARIFA_AUMENTO_UNILATERAL",
            priority="WARNING",
        )
        channels = {r.channel: r.success for r in results}
        assert channels.get("push") is True
        assert channels.get("in_app") is True
        assert sent["user_id"] == _USER
        assert "<h2>" not in sent["body"]          # html vira texto puro
        assert sent["tag"] == "TARIFA_AUMENTO_UNILATERAL"

    def test_info_nao_escala_para_push(self, monkeypatch):
        monkeypatch.setattr(push_sender, "is_configured", lambda: True)
        monkeypatch.setattr(push_sender, "has_active_subscription", lambda uid: True)
        monkeypatch.setattr(
            push_sender, "send_to_user",
            lambda **k: (_ for _ in ()).throw(AssertionError("não deveria enviar")),
        )
        results = deliver(
            user_id=_USER, subject="dica", html_body="<p>x</p>", priority="INFO",
        )
        assert {r.channel for r in results} == {"in_app"}

    def test_sem_inscricao_nao_escala(self, monkeypatch):
        monkeypatch.setattr(push_sender, "is_configured", lambda: True)
        monkeypatch.setattr(push_sender, "has_active_subscription", lambda uid: False)
        results = deliver(
            user_id=_USER, subject="alerta", html_body="<p>x</p>", priority="CRITICAL",
        )
        assert {r.channel for r in results} == {"in_app"}


class TestSendToUser:
    @pytest.fixture
    def _configured(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "pub")
        monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "priv")
        monkeypatch.setattr(
            push_sender, "get_active_subscriptions",
            lambda uid: [push_sender.PushSubscription(
                id="sub1", endpoint="https://fcm.googleapis.com/fcm/send/x", p256dh="p", auth="a",
            )],
        )

    def test_envio_com_sucesso(self, _configured, monkeypatch):
        import pywebpush

        monkeypatch.setattr(pywebpush, "webpush", lambda **k: None)
        monkeypatch.setattr(push_sender, "_mark_success", lambda sid: None)

        sent, failed = push_sender.send_to_user(_USER, "titulo", "corpo")
        assert (sent, failed) == (1, 0)

    def test_http_410_revoga_inscricao(self, _configured, monkeypatch):
        import pywebpush

        class _Resp:
            status_code = 410

        def _dead(**kwargs):
            raise pywebpush.WebPushException("gone", response=_Resp())

        revoked = []
        monkeypatch.setattr(pywebpush, "webpush", _dead)
        monkeypatch.setattr(push_sender, "_revoke", lambda sid: revoked.append(sid))

        sent, failed = push_sender.send_to_user(_USER, "titulo", "corpo")
        assert (sent, failed) == (0, 1)
        assert revoked == ["sub1"]

    def test_envio_nao_segue_redirecionamento(self, _configured, monkeypatch):
        # um 3xx do destino não pode levar o backend para outro host/porta/HTTP
        import pywebpush

        sessoes = []
        monkeypatch.setattr(pywebpush, "webpush", lambda **k: sessoes.append(k.get("requests_session")))
        monkeypatch.setattr(push_sender, "_mark_success", lambda sid: None)

        push_sender.send_to_user(_USER, "titulo", "corpo")
        assert len(sessoes) == 1 and sessoes[0] is not None
        assert sessoes[0].max_redirects == 0

    def test_sem_vapid_desativado(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
        assert push_sender.send_to_user(_USER, "t", "c") == (0, 0)
