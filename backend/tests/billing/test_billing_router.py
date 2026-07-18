# tests/billing/test_billing_router.py
# Endpoints /billing — planos, assinatura, checkout, webhook (assinado)

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.billing.router import router, _service
from app.core.config import settings
from app.core.security import require_owner

USER = "user_billing_test"
WEBHOOK_SECRET = "whsec_router_test"


def _make_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_owner] = lambda user_id: USER
    return TestClient(app)


client = _make_client()


def _signed_headers(payload: bytes) -> dict:
    ts = int(time.time())
    mac = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256)
    return {"Stripe-Signature": f"t={ts},v1={mac.hexdigest()}"}


# ── GET /billing/plans ───────────────────────────────────────────────────────

def test_lista_planos_publica():
    resp = client.get("/billing/plans")
    assert resp.status_code == 200
    plans = {p["plan_id"]: p for p in resp.json()}
    assert set(plans) == {"free", "pro", "total"}
    assert plans["pro"]["price_brl_monthly"] == 19.90
    assert plans["total"]["price_brl_monthly"] == 39.90
    assert plans["free"]["price_brl_monthly"] == 0.0


# ── GET /billing/subscription ────────────────────────────────────────────────

def test_assinatura_default_free():
    with patch.object(_service, "get_record_dict", return_value={
        "plan": "free", "status": "active", "cancel_at_period_end": False,
        "current_period_end": None, "stripe_customer_id": None,
    }):
        resp = client.get(f"/billing/subscription/{USER}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "free"
    assert body["billing_enabled"] is False       # sem STRIPE_SECRET_KEY no teste
    assert body["enforcement_enabled"] is False   # dark launch por default


# ── POST /billing/checkout ───────────────────────────────────────────────────

def test_checkout_sem_stripe_retorna_503():
    resp = client.post(f"/billing/checkout/{USER}", json={"plan": "pro"})
    assert resp.status_code == 503


def test_checkout_com_stripe_retorna_url(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "price_pro", raising=False)
    with patch.object(
        _service.stripe, "create_checkout_session",
        return_value={"id": "cs_1", "url": "https://checkout.stripe.com/cs_1"},
    ) as mock_create:
        resp = client.post(f"/billing/checkout/{USER}", json={"plan": "pro"})
    assert resp.status_code == 200
    assert resp.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert mock_create.call_args.kwargs["user_id"] == USER


def test_checkout_plano_invalido_422():
    resp = client.post(f"/billing/checkout/{USER}", json={"plan": "diamante"})
    assert resp.status_code == 422


# ── POST /billing/webhook ────────────────────────────────────────────────────

@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET, raising=False)


def test_webhook_sem_segredo_503():
    resp = client.post("/billing/webhook", content=b"{}")
    assert resp.status_code == 503


def test_webhook_producao_sem_segredo_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "", raising=False)
    resp = client.post("/billing/webhook", content=b"{}")
    assert resp.status_code == 503


def test_webhook_assinatura_invalida_401(webhook_secret):
    resp = client.post(
        "/billing/webhook", content=b'{"id": "evt"}',
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 401


def test_webhook_valido_processa_evento(webhook_secret):
    event = {"id": "evt_1", "type": "checkout.session.completed",
             "data": {"object": {"client_reference_id": USER}}}
    payload = json.dumps(event).encode()
    with patch.object(_service, "handle_webhook_event", return_value="activated:pro") as h:
        resp = client.post("/billing/webhook", content=payload, headers=_signed_headers(payload))
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "action": "activated:pro"}
    assert h.call_args.args[0]["id"] == "evt_1"


def test_webhook_evento_desconhecido_ignorado(webhook_secret):
    event = {"id": "evt_2", "type": "customer.created", "data": {"object": {}}}
    payload = json.dumps(event).encode()
    resp = client.post("/billing/webhook", content=payload, headers=_signed_headers(payload))
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored:customer.created"
