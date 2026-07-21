"""
app/billing/service.py — Ciclo de vida de assinaturas.

Responsabilidades:
  - Resolver o plano EFETIVO do usuário (registro + status Stripe);
  - Criar sessões de Checkout e de Portal;
  - Processar eventos de webhook (idempotente por event id):
      checkout.session.completed        → ativa o plano
      customer.subscription.updated     → sincroniza status/plano/período
      customer.subscription.deleted     → volta para free
      invoice.payment_failed            → marca past_due (acesso mantido;
                                          o Stripe cancela após as retries)

Sem registro na tabela → free. Status que mantêm o plano pago:
active, trialing, past_due (cortesia até o Stripe desistir das retries).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.billing.plans import PLAN_FREE, PLAN_PRO, PLAN_TOTAL
from app.billing.stripe_client import StripeClient

logger = logging.getLogger(__name__)

_PAID_OK_STATUSES = {"active", "trialing", "past_due"}


class BillingService:
    def __init__(self, stripe: StripeClient | None = None):
        self.stripe = stripe or StripeClient()

    # ── plano efetivo ───────────────────────────────────────────────

    def get_effective_plan(self, user_id: str) -> str:
        """Plano efetivo do usuário — nunca levanta (fallback: free)."""
        record = self._get_record(user_id)
        if record is None:
            return PLAN_FREE
        if record.plan in (PLAN_PRO, PLAN_TOTAL) and record.status in _PAID_OK_STATUSES:
            return record.plan
        return PLAN_FREE

    def get_record_dict(self, user_id: str) -> dict:
        record = self._get_record(user_id)
        if record is None:
            return {
                "plan": PLAN_FREE, "status": "active",
                "cancel_at_period_end": False, "current_period_end": None,
                "stripe_customer_id": None,
            }
        return {
            "plan": self.get_effective_plan(user_id),
            "status": record.status,
            "cancel_at_period_end": bool(record.cancel_at_period_end),
            "current_period_end": record.current_period_end,
            "stripe_customer_id": record.stripe_customer_id,
        }

    @staticmethod
    def _get_record(user_id: str):
        try:
            from app.billing.models_orm import UserSubscription
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                return db.get(UserSubscription, user_id)
        except Exception as exc:
            logger.warning("[Billing] leitura de assinatura falhou user=%s: %s", user_id, exc)
            return None

    # ── checkout / portal ───────────────────────────────────────────

    def create_checkout(self, *, user_id: str, plan_id: str, customer_email: str | None,
                        success_url: str, cancel_url: str) -> dict:
        price_id = self.stripe.price_id_for(plan_id)
        if not price_id:
            from app.billing.stripe_client import StripeNaoConfigurado

            raise StripeNaoConfigurado(
                f"STRIPE_PRICE_{plan_id.upper()}_MONTHLY não configurado."
            )
        return self.stripe.create_checkout_session(
            price_id=price_id,
            user_id=user_id,
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
        )

    def create_portal(self, *, user_id: str, return_url: str) -> dict:
        record = self._get_record(user_id)
        if record is None or not record.stripe_customer_id:
            from app.billing.stripe_client import StripeNaoConfigurado

            raise StripeNaoConfigurado("Usuário sem assinatura Stripe ativa.")
        return self.stripe.create_portal_session(
            customer_id=record.stripe_customer_id, return_url=return_url
        )

    # ── webhook ─────────────────────────────────────────────────────

    def handle_webhook_event(self, event: dict) -> str:
        """Processa um evento já autenticado. Retorna ação executada (log).
        Idempotente: event id repetido para o mesmo usuário é ignorado."""
        event_id = str(event.get("id") or "")
        event_type = str(event.get("type") or "")
        obj = (event.get("data") or {}).get("object") or {}

        handler = {
            "checkout.session.completed": self._on_checkout_completed,
            "customer.subscription.updated": self._on_subscription_updated,
            "customer.subscription.deleted": self._on_subscription_deleted,
            "invoice.payment_failed": self._on_payment_failed,
        }.get(event_type)

        if handler is None:
            return f"ignored:{event_type}"
        return handler(event_id, obj)

    # Cada handler resolve o user_id do jeito que o objeto permite —
    # nunca confia em user_id vindo de fora sem vínculo Stripe.

    def _on_checkout_completed(self, event_id: str, session: dict) -> str:
        user_id = str(session.get("client_reference_id") or "")
        if not user_id:
            logger.warning("[Billing] checkout sem client_reference_id — ignorado")
            return "ignored:no_user"
        subscription_id = session.get("subscription")
        customer_id = session.get("customer")

        plan, status, period_end, cancel_at_end = PLAN_PRO, "active", None, False
        if subscription_id:
            try:
                sub = self.stripe.get_subscription(str(subscription_id))
                plan = self._plan_from_subscription(sub) or plan
                status = str(sub.get("status") or status)
                period_end = self._period_end(sub)
                cancel_at_end = bool(sub.get("cancel_at_period_end"))
            except Exception as exc:
                logger.warning("[Billing] retrieve subscription falhou: %s", exc)

        self._upsert(
            user_id=user_id, event_id=event_id, plan=plan, status=status,
            customer_id=customer_id, subscription_id=subscription_id,
            period_end=period_end, cancel_at_end=cancel_at_end,
        )
        logger.info("[Billing] assinatura ativada user=%s plan=%s", user_id, plan)
        return f"activated:{plan}"

    def _on_subscription_updated(self, event_id: str, sub: dict) -> str:
        user_id = self._user_by_subscription(sub)
        if not user_id:
            return "ignored:unknown_subscription"
        self._upsert(
            user_id=user_id, event_id=event_id,
            plan=self._plan_from_subscription(sub) or PLAN_PRO,
            status=str(sub.get("status") or "active"),
            customer_id=sub.get("customer"),
            subscription_id=sub.get("id"),
            period_end=self._period_end(sub),
            cancel_at_end=bool(sub.get("cancel_at_period_end")),
        )
        return "updated"

    def _on_subscription_deleted(self, event_id: str, sub: dict) -> str:
        user_id = self._user_by_subscription(sub)
        if not user_id:
            return "ignored:unknown_subscription"
        self._upsert(
            user_id=user_id, event_id=event_id, plan=PLAN_FREE, status="canceled",
            customer_id=sub.get("customer"), subscription_id=sub.get("id"),
            period_end=None, cancel_at_end=False,
        )
        logger.info("[Billing] assinatura cancelada user=%s", user_id)
        return "canceled"

    def _on_payment_failed(self, event_id: str, invoice: dict) -> str:
        sub_id = invoice.get("subscription")
        if not sub_id:
            return "ignored:no_subscription"
        user_id = self._user_by_subscription({"id": sub_id})
        if not user_id:
            return "ignored:unknown_subscription"
        record = self._get_record(user_id)
        if record is None:
            return "ignored:no_record"
        self._upsert(
            user_id=user_id, event_id=event_id, plan=record.plan, status="past_due",
            customer_id=record.stripe_customer_id, subscription_id=sub_id,
            period_end=record.current_period_end,
            cancel_at_end=bool(record.cancel_at_period_end),
        )
        return "past_due"

    # ── helpers ─────────────────────────────────────────────────────

    def _plan_from_subscription(self, sub: dict) -> str | None:
        """Mapeia o price da assinatura para pro/total via env."""
        items = ((sub.get("items") or {}).get("data")) or []
        price_ids = {
            str(((item.get("price") or {}).get("id")) or "") for item in items
        }
        if self.stripe.price_id_for(PLAN_TOTAL) in price_ids:
            return PLAN_TOTAL
        if self.stripe.price_id_for(PLAN_PRO) in price_ids:
            return PLAN_PRO
        return None

    @staticmethod
    def _period_end(sub: dict):
        raw = sub.get("current_period_end")
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc) if raw else None
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _user_by_subscription(sub: dict) -> str | None:
        sub_id = str(sub.get("id") or "")
        if not sub_id:
            return None
        try:
            from app.billing.models_orm import UserSubscription
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                row = (
                    db.query(UserSubscription)
                    .filter(UserSubscription.stripe_subscription_id == sub_id)
                    .first()
                )
                return row.user_id if row else None
        except Exception as exc:
            logger.warning("[Billing] busca por subscription=%s falhou: %s", sub_id, exc)
            return None

    @staticmethod
    def _upsert(*, user_id: str, event_id: str, plan: str, status: str,
                customer_id, subscription_id, period_end, cancel_at_end: bool) -> None:
        from app.billing.models_orm import UserSubscription
        from app.core.database import SessionLocal

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            record = db.get(UserSubscription, user_id)
            if record is not None and event_id and record.last_event_id == event_id:
                return  # evento repetido (retry do Stripe) — idempotência
            if record is None:
                record = UserSubscription(user_id=user_id, created_at=now)
                db.add(record)
            record.plan = plan
            record.status = status
            record.stripe_customer_id = customer_id or record.stripe_customer_id
            record.stripe_subscription_id = subscription_id or record.stripe_subscription_id
            record.current_period_end = period_end
            record.cancel_at_period_end = cancel_at_end
            record.updated_at = now
            record.last_event_id = event_id or record.last_event_id
            db.commit()


__all__ = ["BillingService"]
