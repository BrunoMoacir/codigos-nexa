"""
app/billing/stripe_client.py — Cliente Stripe minimalista (REST via httpx).

Por que não o SDK oficial: o projeto mantém dependências enxutas (pip-audit
no CI) e usa apenas 4 chamadas da API — Checkout Session, Billing Portal,
Subscription retrieve e verificação de assinatura de webhook. A API do
Stripe é REST puro com form-encoding; o SDK não adiciona nada essencial.

Assinatura de webhook (esquema oficial Stripe-Signature):
  header:  t=<timestamp>,v1=<hmac>,...
  hmac:    HMAC-SHA256(secret, f"{t}.{payload_bruto}")
  Tolerância de replay: _SIGNATURE_TOLERANCE_SECONDS.

Configuração (Settings): STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
STRIPE_PRICE_PRO_MONTHLY, STRIPE_PRICE_TOTAL_MONTHLY.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 20.0
_SIGNATURE_TOLERANCE_SECONDS = 300  # 5 min, mesmo default do SDK oficial


class StripeNaoConfigurado(Exception):
    """STRIPE_SECRET_KEY ausente — billing indisponível neste ambiente."""


class StripeIndisponivel(Exception):
    """Falha de rede/5xx na API do Stripe."""


class StripeAssinaturaInvalida(Exception):
    """Webhook com assinatura ausente, inválida ou expirada."""


class StripeClient:
    """`transport` é injetável para testes (httpx.MockTransport)."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    # ── configuração ────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))

    def price_id_for(self, plan_id: str) -> str | None:
        return {
            "pro": getattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "") or None,
            "total": getattr(settings, "STRIPE_PRICE_TOTAL_MONTHLY", "") or None,
        }.get(plan_id)

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict:
        if not self.is_configured:
            raise StripeNaoConfigurado(
                "STRIPE_SECRET_KEY não configurada — defina as chaves do Stripe."
            )
        try:
            with httpx.Client(
                base_url=_API_BASE,
                timeout=_TIMEOUT,
                auth=(settings.STRIPE_SECRET_KEY, ""),
                transport=self._transport,
            ) as client:
                resp = client.request(method, path, data=data)
        except httpx.HTTPError as exc:
            raise StripeIndisponivel(f"Falha de rede na API Stripe: {exc}") from exc

        if resp.status_code >= 500:
            raise StripeIndisponivel(f"Stripe retornou HTTP {resp.status_code}")
        payload = resp.json()
        if resp.status_code >= 400:
            message = (payload.get("error") or {}).get("message", f"HTTP {resp.status_code}")
            raise StripeIndisponivel(f"Stripe recusou a chamada: {message}")
        return payload

    # ── chamadas usadas pela Nexa ───────────────────────────────────

    def create_checkout_session(
        self,
        *,
        price_id: str,
        user_id: str,
        customer_email: str | None,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Sessão de Checkout em modo assinatura. `client_reference_id`
        carrega o user_id — é como o webhook resolve o dono da assinatura."""
        data: dict[str, Any] = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "client_reference_id": user_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": "true",
            "locale": "pt-BR",
        }
        if customer_email:
            data["customer_email"] = customer_email
        return self._request("POST", "/checkout/sessions", data)

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict:
        """Portal do cliente (trocar cartão, cancelar, trocar plano)."""
        return self._request(
            "POST", "/billing_portal/sessions",
            {"customer": customer_id, "return_url": return_url},
        )

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}")

    # ── verificação de assinatura de webhook ────────────────────────

    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature_header: str | None,
        secret: str,
        *,
        tolerance_seconds: int = _SIGNATURE_TOLERANCE_SECONDS,
        now: float | None = None,
    ) -> None:
        """Valida o header Stripe-Signature. Levanta StripeAssinaturaInvalida.
        Comparação em tempo constante; rejeita timestamps fora da tolerância
        (proteção contra replay)."""
        if not secret:
            raise StripeAssinaturaInvalida("Segredo de webhook não configurado")
        if not signature_header:
            raise StripeAssinaturaInvalida("Header Stripe-Signature ausente")

        timestamp: str | None = None
        candidates: list[str] = []
        for part in signature_header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                candidates.append(value)

        if not timestamp or not candidates:
            raise StripeAssinaturaInvalida("Header Stripe-Signature malformado")

        try:
            ts = float(timestamp)
        except ValueError:
            raise StripeAssinaturaInvalida("Timestamp inválido no Stripe-Signature")

        current = now if now is not None else time.time()
        if abs(current - ts) > tolerance_seconds:
            raise StripeAssinaturaInvalida("Assinatura expirada (possível replay)")

        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, c) for c in candidates):
            raise StripeAssinaturaInvalida("Assinatura do webhook não confere")


__all__ = [
    "StripeClient",
    "StripeNaoConfigurado",
    "StripeIndisponivel",
    "StripeAssinaturaInvalida",
]
