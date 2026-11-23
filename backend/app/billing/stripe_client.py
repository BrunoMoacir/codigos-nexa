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
STRIPE_API_VERSION e, opcionalmente, STRIPE_PRICE_PRO_MONTHLY /
STRIPE_PRICE_TOTAL_MONTHLY. Sem os IDs no ambiente, os prices são achados
pelo lookup_key (plans.PRICE_LOOKUP_KEYS) e guardados em memória por 10 min.

Toda chamada leva `Stripe-Version` fixo: a resposta não muda de formato quando
a conta é atualizada no dashboard. Criações levam `Idempotency-Key` quando o
chamador passa uma — um clique duplo em "Assinar" devolve a MESMA sessão.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 20.0
_SIGNATURE_TOLERANCE_SECONDS = 300  # 5 min, mesmo default do SDK oficial
_PRICE_CACHE_SECONDS = 600

# plano → (price_id, guardado_em) para prices achados pelo lookup_key
_price_cache: dict[str, tuple[str, float]] = {}


class StripeNaoConfigurado(Exception):
    """STRIPE_SECRET_KEY ausente — billing indisponível neste ambiente."""


class StripeIndisponivel(Exception):
    """Falha de rede/5xx na API do Stripe."""


class StripeNaoEncontrado(StripeIndisponivel):
    """O recurso pedido não existe no Stripe (HTTP 404)."""


class StripeAssinaturaInvalida(Exception):
    """Webhook com assinatura ausente, inválida ou expirada."""


_ID_STRIPE = re.compile(r"[A-Za-z0-9_]{3,255}")


def _id_seguro(valor: str, prefixo: str) -> str:
    """IDs que entram no CAMINHO da URL: `cs_..`, `sub_..`. Um session_id
    vindo do navegador como "../customers" desviaria a chamada para outro
    recurso da API — só letras, dígitos e _ com o prefixo esperado passam."""
    valor = str(valor or "")
    if not valor.startswith(prefixo) or not _ID_STRIPE.fullmatch(valor):
        raise ValueError(f"ID Stripe inválido (esperado {prefixo}…)")
    return valor


class StripeClient:
    """`transport` é injetável para testes (httpx.MockTransport)."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    # ── configuração ────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))

    @property
    def is_ready(self) -> bool:
        """Dá para COBRAR de verdade: chave da API e segredo do webhook.
        Sem o segredo, o pagamento acontece no Stripe mas a assinatura nunca
        chega ao app — o usuário pagaria e continuaria bloqueado."""
        return self.is_configured and bool(getattr(settings, "STRIPE_WEBHOOK_SECRET", ""))

    @staticmethod
    def _env_price_ids() -> dict[str, str]:
        return {
            "pro": getattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "") or "",
            "total": getattr(settings, "STRIPE_PRICE_TOTAL_MONTHLY", "") or "",
        }

    def price_id_for(self, plan_id: str) -> str | None:
        """Price do plano: o ID do ambiente, ou o achado pelo lookup_key."""
        from app.billing.plans import PRICE_LOOKUP_KEYS

        do_ambiente = self._env_price_ids().get(plan_id)
        if do_ambiente:
            return do_ambiente
        lookup_key = PRICE_LOOKUP_KEYS.get(plan_id)
        if not lookup_key or not self.is_configured:
            return None
        guardado = _price_cache.get(plan_id)
        if guardado and time.monotonic() - guardado[1] < _PRICE_CACHE_SECONDS:
            return guardado[0]
        try:
            resposta = self._request(
                "GET", "/prices",
                params={"lookup_keys[]": lookup_key, "active": "true", "limit": 1},
            )
        except (StripeIndisponivel, StripeNaoConfigurado) as exc:
            logger.warning("[Stripe] price %s não resolvido: %s", lookup_key, exc)
            return None
        itens = resposta.get("data") or []
        if not itens:
            logger.error("[Stripe] nenhum price ativo com lookup_key=%s — rode scripts/stripe_setup.py", lookup_key)
            return None
        price_id = str(itens[0].get("id") or "")
        if price_id:
            _price_cache[plan_id] = (price_id, time.monotonic())
        return price_id or None

    def plan_for_price(self, price: dict) -> str | None:
        """Plano de um price da assinatura — pelo lookup_key (estável) ou
        pelo ID configurado no ambiente. Price desconhecido → None: nunca
        concede plano pago por um price que não é nosso."""
        from app.billing.plans import PRICE_LOOKUP_KEYS

        if not isinstance(price, dict):
            return None
        lookup_key = price.get("lookup_key")
        for plano, chave in PRICE_LOOKUP_KEYS.items():
            if lookup_key and lookup_key == chave:
                return plano
        price_id = str(price.get("id") or "")
        if price_id:
            for plano, configurado in self._env_price_ids().items():
                if configurado and configurado == price_id:
                    return plano
            for plano, (guardado, _) in _price_cache.items():
                if guardado == price_id:
                    return plano
        return None

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        if not self.is_configured:
            raise StripeNaoConfigurado(
                "STRIPE_SECRET_KEY não configurada — defina as chaves do Stripe."
            )
        headers = {"Stripe-Version": getattr(settings, "STRIPE_API_VERSION", "") or "2024-06-20"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(
                base_url=_API_BASE,
                timeout=_TIMEOUT,
                auth=(settings.STRIPE_SECRET_KEY, ""),
                transport=self._transport,
                headers=headers,
            ) as client:
                resp = client.request(method, path, data=data, params=params)
        except httpx.HTTPError as exc:
            raise StripeIndisponivel(f"Falha de rede na API Stripe: {exc}") from exc

        if resp.status_code >= 500:
            raise StripeIndisponivel(f"Stripe retornou HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise StripeIndisponivel(f"Resposta inválida do Stripe (HTTP {resp.status_code})") from exc
        if resp.status_code >= 400:
            message = (payload.get("error") or {}).get("message", f"HTTP {resp.status_code}")
            if resp.status_code == 404:
                raise StripeNaoEncontrado(f"Stripe: {message}")
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
        customer_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Sessão de Checkout em modo assinatura.

        O dono vai em três lugares, todos escritos pelo servidor a partir do
        token (nunca do corpo da requisição): `client_reference_id` (lido no
        checkout.session.completed), `metadata[user_id]` da sessão e da
        assinatura (lido em qualquer evento de assinatura, inclusive se o
        webhook do checkout se perder). Quem já é cliente reaproveita o
        customer: sem isso cada checkout criava um cliente novo no Stripe."""
        data: dict[str, Any] = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "client_reference_id": user_id,
            "metadata[user_id]": user_id,
            "subscription_data[metadata][user_id]": user_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": "true",
            "locale": "pt-BR",
        }
        if customer_id:
            data["customer"] = customer_id
        elif customer_email:
            data["customer_email"] = customer_email
        return self._request("POST", "/checkout/sessions", data, idempotency_key=idempotency_key)

    def get_checkout_session(self, session_id: str) -> dict:
        return self._request("GET", f"/checkout/sessions/{_id_seguro(session_id, 'cs_')}")

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict:
        """Portal do cliente (trocar cartão, cancelar, trocar plano)."""
        data = {"customer": customer_id, "return_url": return_url}
        configuracao = getattr(settings, "STRIPE_PORTAL_CONFIGURATION", "") or ""
        if configuracao:
            data["configuration"] = configuracao
        return self._request("POST", "/billing_portal/sessions", data)

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{_id_seguro(subscription_id, 'sub_')}")

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
    "StripeNaoEncontrado",
    "StripeAssinaturaInvalida",
]
