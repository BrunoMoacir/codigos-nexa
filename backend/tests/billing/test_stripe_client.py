# tests/billing/test_stripe_client.py
# Cliente Stripe (REST httpx) — checkout, portal e assinatura de webhook

import hashlib
import hmac
import time

import httpx
import pytest

from app.core.config import settings
from app.billing.stripe_client import (
    StripeAssinaturaInvalida,
    StripeClient,
    StripeIndisponivel,
    StripeNaoConfigurado,
)

SECRET = "whsec_teste_123"


def _sign(payload: bytes, secret: str = SECRET, ts: float | None = None) -> str:
    ts = ts if ts is not None else time.time()
    mac = hmac.new(secret.encode(), f"{int(ts)}.".encode() + payload, hashlib.sha256)
    return f"t={int(ts)},v1={mac.hexdigest()}"


@pytest.fixture
def stripe_configured(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_abc", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "price_pro", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_TOTAL_MONTHLY", "price_total", raising=False)


# ── configuração ─────────────────────────────────────────────────────────────

def test_nao_configurado_levanta(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "", raising=False)
    with pytest.raises(StripeNaoConfigurado):
        StripeClient().create_portal_session(customer_id="cus_1", return_url="http://x")


def test_price_id_mapping(stripe_configured):
    c = StripeClient()
    assert c.price_id_for("pro") == "price_pro"
    assert c.price_id_for("total") == "price_total"
    assert c.price_id_for("free") is None


# ── checkout ─────────────────────────────────────────────────────────────────

def test_checkout_session_form_encoded(stripe_configured):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.com/cs_1"})

    session = StripeClient(transport=httpx.MockTransport(handler)).create_checkout_session(
        price_id="price_pro",
        user_id="user_42",
        customer_email=None,
        success_url="https://app/success",
        cancel_url="https://app/cancel",
    )
    assert session["url"].startswith("https://checkout.stripe.com/")
    assert seen["path"] == "/v1/checkout/sessions"
    assert "mode=subscription" in seen["body"]
    assert "client_reference_id=user_42" in seen["body"]
    assert seen["auth"].startswith("Basic ")  # basic auth com a secret key


def test_erro_4xx_vira_indisponivel_com_mensagem(stripe_configured):
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "No such price"}})

    with pytest.raises(StripeIndisponivel, match="No such price"):
        StripeClient(transport=httpx.MockTransport(handler)).create_checkout_session(
            price_id="price_x", user_id="u", customer_email=None,
            success_url="http://s", cancel_url="http://c",
        )


# ── webhook signature ────────────────────────────────────────────────────────

def test_assinatura_valida_passa():
    payload = b'{"id": "evt_1"}'
    StripeClient.verify_webhook_signature(payload, _sign(payload), SECRET)


def test_assinatura_com_payload_alterado_falha():
    payload = b'{"id": "evt_1"}'
    header = _sign(payload)
    with pytest.raises(StripeAssinaturaInvalida):
        StripeClient.verify_webhook_signature(b'{"id": "evt_TAMPERED"}', header, SECRET)


def test_assinatura_com_segredo_errado_falha():
    payload = b'{}'
    with pytest.raises(StripeAssinaturaInvalida):
        StripeClient.verify_webhook_signature(payload, _sign(payload, "whsec_outro"), SECRET)


def test_replay_fora_da_tolerancia_falha():
    payload = b'{}'
    velho = _sign(payload, ts=time.time() - 3600)
    with pytest.raises(StripeAssinaturaInvalida, match="expirada"):
        StripeClient.verify_webhook_signature(payload, velho, SECRET)


@pytest.mark.parametrize("header", [None, "", "v1=abc", "t=123", "lixo"])
def test_header_ausente_ou_malformado_falha(header):
    with pytest.raises(StripeAssinaturaInvalida):
        StripeClient.verify_webhook_signature(b"{}", header, SECRET)
