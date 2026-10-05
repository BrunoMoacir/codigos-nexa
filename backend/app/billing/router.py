"""
app/billing/router.py — Endpoints de billing (Stripe).

GET  /billing/plans                      — catálogo público de planos
GET  /billing/subscription/{user_id}     — plano efetivo + uso dos limites
POST /billing/checkout/{user_id}         — sessão de Checkout (pro|total)
POST /billing/portal/{user_id}           — portal do cliente (trocar/cancelar)
POST /billing/webhook                    — eventos Stripe (assinado; fail-closed
                                           em produção sem segredo, como o Pluggy)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.billing.gating import enforcement_enabled, usage_snapshot
from app.billing.models import (
    CheckoutIn,
    CheckoutOut,
    PlanOut,
    PortalOut,
    SubscriptionOut,
)
from app.billing.plans import PLANS
from app.billing.service import BillingService
from app.billing.stripe_client import (
    StripeAssinaturaInvalida,
    StripeClient,
    StripeIndisponivel,
    StripeNaoConfigurado,
)
from app.core.config import settings
from app.core.security import require_owner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing (Stripe)"])

_service = BillingService()


@router.get("/plans", response_model=list[PlanOut])
def list_plans() -> list[PlanOut]:
    """Catálogo público de planos (Free/Pro/Total)."""
    return [
        PlanOut(
            plan_id=p.plan_id, name=p.name,
            price_brl_monthly=p.price_brl_monthly,
            tagline=p.tagline, features=p.features,
        )
        for p in PLANS.values()
    ]


@router.get("/subscription/{user_id}", response_model=SubscriptionOut)
def get_subscription(user_id: str = Depends(require_owner)) -> SubscriptionOut:
    """Plano efetivo do usuário + uso atual dos limites do plano."""
    record = _service.get_record_dict(user_id)
    return SubscriptionOut(
        user_id=user_id,
        plan=record["plan"],
        status=record["status"],
        cancel_at_period_end=record["cancel_at_period_end"],
        current_period_end=record["current_period_end"],
        usage=usage_snapshot(user_id),
        billing_enabled=_service.stripe.is_configured,
        enforcement_enabled=enforcement_enabled(),
    )


def _frontend_base() -> str:
    return (getattr(settings, "FRONTEND_BASE_URL", "") or "http://localhost:3000").rstrip("/")


@router.post("/checkout/{user_id}", response_model=CheckoutOut)
def create_checkout(
    body: CheckoutIn,
    user_id: str = Depends(require_owner),
) -> CheckoutOut:
    """Cria a sessão de Checkout do Stripe para assinar Pro ou Total."""
    base = _frontend_base()
    try:
        session = _service.create_checkout(
            user_id=user_id,
            plan_id=body.plan,
            customer_email=None,  # Stripe coleta no checkout; evita expor email na URL
            # Rotas que o app React tem: a tela de Planos lê ?checkout= na volta.
            # As antigas (/billing/success, /billing/cancel) não existiam em lugar
            # nenhum — o usuário pagava e caía numa página em branco.
            success_url=f"{base}/planos?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/planos?checkout=cancel",
        )
    except StripeNaoConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except StripeIndisponivel as exc:
        logger.warning("[Billing] checkout indisponível user=%s: %s", user_id, exc)
        raise HTTPException(status_code=503, detail="Stripe indisponível no momento.")

    return CheckoutOut(checkout_url=session.get("url", ""), session_id=session.get("id", ""))


@router.post("/portal/{user_id}", response_model=PortalOut)
def create_portal(user_id: str = Depends(require_owner)) -> PortalOut:
    """Portal do cliente Stripe (trocar cartão, plano ou cancelar)."""
    base = _frontend_base()
    try:
        session = _service.create_portal(user_id=user_id, return_url=f"{base}/planos")
    except StripeNaoConfigurado as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except StripeIndisponivel as exc:
        logger.warning("[Billing] portal indisponível user=%s: %s", user_id, exc)
        raise HTTPException(status_code=503, detail="Stripe indisponível no momento.")
    return PortalOut(portal_url=session.get("url", ""))


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """
    Webhook do Stripe. Segurança no padrão do webhook Pluggy:
      - assinatura verificada em tempo constante (Stripe-Signature v1);
      - produção SEM segredo configurado → 503 fail-closed;
      - identidade do usuário resolvida pelo vínculo Stripe, nunca do payload.
    """
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""
    app_env = getattr(settings, "APP_ENV", "development")
    if not secret:
        if app_env == "production":
            logger.error("[Billing] webhook sem STRIPE_WEBHOOK_SECRET em produção — recusado")
            raise HTTPException(status_code=503, detail="Webhook não configurado.")
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET não configurado.")

    payload = await request.body()
    try:
        StripeClient.verify_webhook_signature(
            payload, request.headers.get("Stripe-Signature"), secret
        )
    except StripeAssinaturaInvalida as exc:
        logger.warning("[Billing] webhook rejeitado: %s", exc)
        raise HTTPException(status_code=401, detail="Assinatura inválida.")

    import json

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Payload inválido.")

    action = _service.handle_webhook_event(event)
    logger.info("[Billing] webhook %s → %s", event.get("type"), action)
    return {"received": True, "action": action}


__all__ = ["router"]
