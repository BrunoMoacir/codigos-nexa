"""
app/billing/service.py — Ciclo de vida de assinaturas.

Responsabilidades:
  - Resolver o plano EFETIVO do usuário (registro + status Stripe);
  - Criar sessões de Checkout e de Portal (e confirmar a volta do Checkout);
  - Processar eventos de webhook.

Regra central do webhook: o evento só diz QUAL assinatura mudou; o ESTADO vem
sempre de uma consulta ao Stripe (fonte da verdade). Isso resolve de uma vez:
  - eventos fora de ordem — o Stripe não garante ordem, e um `updated` antigo
    que chegasse depois do `deleted` devolvia o plano pago a quem cancelou;
  - pagamento assíncrono (boleto) — o checkout completa com a assinatura
    `incomplete` e o plano só libera quando ela vira `active`;
  - formato de payload — a assinatura é lida com a versão de API fixada.
Se a consulta falhar, a exceção sobe, o webhook responde 500 e o Stripe tenta
de novo. Nunca se presume `active`.

Eventos repetidos: tabela billing_webhook_events (event id único). Como o
processamento é uma sincronização idempotente, um repetido que escape da
tabela (corrida entre duas entregas) só reescreve o mesmo estado.

Status que mantêm o plano pago: active, trialing e past_due — este com
cortesia limitada: até GRACE_PAST_DUE depois do fim do período pago, para não
cortar alguém por falha transitória de cartão, nem manter para sempre quem
nunca pagou se um webhook de cancelamento se perder.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

from app.billing.plans import PLAN_FREE, PLAN_PRO, PLAN_TOTAL, plan_satisfies
from app.billing.stripe_client import StripeClient, StripeNaoConfigurado

logger = logging.getLogger(__name__)

_PAID_OK_STATUSES = {"active", "trialing", "past_due"}
GRACE_PAST_DUE = timedelta(days=7)

# Eventos que mudam o estado de uma assinatura. Qualquer outro é ignorado
# (respondido 200 para o Stripe não insistir).
_EVENTOS_DE_CHECKOUT = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
}
_EVENTOS_DE_ASSINATURA = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
}
_EVENTOS_DE_FATURA = {
    "invoice.paid",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
}
EVENTOS_TRATADOS = _EVENTOS_DE_CHECKOUT | _EVENTOS_DE_ASSINATURA | _EVENTOS_DE_FATURA


class AssinaturaJaAtiva(Exception):
    """O usuário já tem assinatura paga: trocar de plano é pelo portal.
    Abrir um segundo checkout criaria uma segunda cobrança mensal."""

    def __init__(self, plano: str):
        super().__init__(f"Assinatura {plano} já ativa — use o portal para trocar de plano.")
        self.plano = plano


class CheckoutDeOutroUsuario(Exception):
    """A sessão de checkout informada pertence a outra conta."""


class BillingService:
    def __init__(self, stripe: StripeClient | None = None):
        self.stripe = stripe or StripeClient()

    # ── plano efetivo ───────────────────────────────────────────────

    def get_effective_plan(self, user_id: str) -> str:
        """Plano efetivo do usuário — nunca levanta (fallback: free)."""
        return self._plano_efetivo(self._get_record(user_id))

    @staticmethod
    def _plano_efetivo(record, agora: datetime | None = None) -> str:
        if record is None or record.plan not in (PLAN_PRO, PLAN_TOTAL):
            return PLAN_FREE
        if record.status in ("active", "trialing"):
            return record.plan
        if record.status == "past_due":
            fim = record.current_period_end
            if fim is None:
                return record.plan
            if fim.tzinfo is None:
                fim = fim.replace(tzinfo=timezone.utc)
            agora = agora or datetime.now(timezone.utc)
            if agora <= fim + GRACE_PAST_DUE:
                return record.plan
        return PLAN_FREE

    def tem_assinatura_paga(self, user_id: str) -> str | None:
        """Plano pago vigente (pro/total) ou None."""
        plano = self.get_effective_plan(user_id)
        return plano if plano != PLAN_FREE else None

    def get_record_dict(self, user_id: str) -> dict:
        record = self._get_record(user_id)
        if record is None:
            return {
                "plan": PLAN_FREE, "status": "active",
                "cancel_at_period_end": False, "current_period_end": None,
                "stripe_customer_id": None,
            }
        return {
            "plan": self._plano_efetivo(record),
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
        pago = self.tem_assinatura_paga(user_id)
        if pago:
            raise AssinaturaJaAtiva(pago)

        price_id = self.stripe.price_id_for(plan_id)
        if not price_id:
            raise StripeNaoConfigurado(
                f"Price do plano {plan_id} não encontrado — defina STRIPE_PRICE_{plan_id.upper()}_MONTHLY "
                "ou rode scripts/stripe_setup.py."
            )

        record = self._get_record(user_id)
        # Mesmo usuário + mesmo plano na mesma janela de 10 min → mesma chave:
        # o Stripe devolve a MESMA sessão para um clique duplo.
        janela = int(time.time() // 600)
        chave = hashlib.sha256(f"checkout:{user_id}:{plan_id}:{janela}".encode()).hexdigest()[:48]
        return self.stripe.create_checkout_session(
            price_id=price_id,
            user_id=user_id,
            customer_email=customer_email,
            customer_id=getattr(record, "stripe_customer_id", None) or None,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=chave,
        )

    def create_portal(self, *, user_id: str, return_url: str) -> dict:
        record = self._get_record(user_id)
        if record is None or not record.stripe_customer_id:
            raise StripeNaoConfigurado("Usuário sem assinatura Stripe ativa.")
        return self.stripe.create_portal_session(
            customer_id=record.stripe_customer_id, return_url=return_url
        )

    def confirm_checkout(self, *, user_id: str, session_id: str) -> str:
        """
        Volta do Checkout (/planos?checkout=success&session_id=…): sincroniza na
        hora, sem esperar o webhook — que pode levar segundos ou minutos.

        A sessão é lida NO STRIPE e só vale se `client_reference_id` for o
        próprio usuário: um session_id de outra conta não muda nada aqui.
        """
        session = self.stripe.get_checkout_session(session_id)
        if str(session.get("client_reference_id") or "") != user_id:
            raise CheckoutDeOutroUsuario("Sessão de checkout de outra conta.")
        sub_id = session.get("subscription")
        if isinstance(sub_id, dict):
            sub_id = sub_id.get("id")
        if session.get("mode") == "subscription" and sub_id:
            self.sync_subscription(str(sub_id), user_hint=user_id, event_id="")
        return self.get_effective_plan(user_id)

    # ── webhook ─────────────────────────────────────────────────────

    def handle_webhook_event(self, event: dict) -> str:
        """Processa um evento já autenticado. Retorna a ação executada (log).
        Exceções sobem: o router responde 500 e o Stripe reenvia."""
        event_id = str(event.get("id") or "")
        event_type = str(event.get("type") or "")
        obj = (event.get("data") or {}).get("object") or {}

        if event_type not in EVENTOS_TRATADOS:
            return f"ignored:{event_type}"
        if event_id and self._ja_processado(event_id):
            return "duplicate"

        if event_type in _EVENTOS_DE_CHECKOUT:
            acao = self._on_checkout(event_id, obj)
        elif event_type in _EVENTOS_DE_ASSINATURA:
            acao = self.sync_subscription(str(obj.get("id") or ""), user_hint=None, event_id=event_id)
        else:
            sub_id = self._assinatura_da_fatura(obj)
            acao = (
                self.sync_subscription(sub_id, user_hint=None, event_id=event_id)
                if sub_id else "ignored:no_subscription"
            )

        if event_id:
            self._marcar_processado(event_id, event_type)
        return acao

    def _on_checkout(self, event_id: str, session: dict) -> str:
        if session.get("mode") not in (None, "subscription"):
            return "ignored:not_subscription"
        user_id = str(session.get("client_reference_id") or "")
        if not user_id:
            logger.warning("[Billing] checkout sem client_reference_id — ignorado")
            return "ignored:no_user"
        sub_id = session.get("subscription")
        if isinstance(sub_id, dict):
            sub_id = sub_id.get("id")
        if not sub_id:
            return "ignored:no_subscription"
        return self.sync_subscription(str(sub_id), user_hint=user_id, event_id=event_id)

    @staticmethod
    def _assinatura_da_fatura(invoice: dict) -> str:
        """`invoice.subscription` até a API 2025-03-31.basil; depois,
        `invoice.parent.subscription_details.subscription`."""
        sub = invoice.get("subscription")
        if not sub:
            parent = invoice.get("parent") or {}
            sub = (parent.get("subscription_details") or {}).get("subscription")
        if isinstance(sub, dict):
            sub = sub.get("id")
        return str(sub or "")

    def sync_subscription(self, sub_id: str, *, user_hint: str | None, event_id: str) -> str:
        """Lê a assinatura no Stripe e grava o estado atual dela."""
        if not sub_id:
            return "ignored:no_subscription"
        sub = self.stripe.get_subscription(sub_id)  # falha → exceção → Stripe reenvia

        user_id = self._dono_da_assinatura(sub, user_hint)
        if not user_id:
            logger.error("[Billing] assinatura %s sem dono resolvível — ignorada", sub_id)
            return "ignored:unknown_owner"

        status = str(sub.get("status") or "incomplete")
        plano = self._plan_from_subscription(sub)
        if plano is None:
            # Price que não é nosso (ou lookup_key apagado): registra, mas não
            # concede plano pago por algo que não reconhecemos.
            logger.error("[Billing] assinatura %s com price desconhecido — tratada como free", sub_id)
            plano = PLAN_FREE

        record = self._get_record(user_id)
        if record is not None and record.stripe_subscription_id and record.stripe_subscription_id != sub_id:
            registrada_vale = self._plano_efetivo(record) != PLAN_FREE
            if status not in _PAID_OK_STATUSES and registrada_vale:
                # evento de uma assinatura antiga/abandonada: não derruba a vigente
                return "ignored:other_subscription"
            if status in _PAID_OK_STATUSES and registrada_vale:
                logger.error(
                    "[Billing] user=%s com duas assinaturas pagas (%s e %s) — cobrança dupla, verifique no Stripe",
                    user_id, record.stripe_subscription_id, sub_id,
                )

        self._upsert(
            user_id=user_id, event_id=event_id, plan=plano, status=status,
            customer_id=self._id_de(sub.get("customer")),
            subscription_id=sub_id,
            period_end=self._period_end(sub),
            cancel_at_end=bool(sub.get("cancel_at_period_end")),
        )
        logger.info("[Billing] assinatura sincronizada user=%s plan=%s status=%s", user_id, plano, status)
        return f"synced:{plano}:{status}"

    def _dono_da_assinatura(self, sub: dict, user_hint: str | None) -> str | None:
        """
        Quem é o dono, por ordem de confiança — todas as fontes foram escritas
        pelo SERVIDOR (nada vem do usuário):
          1. o registro que já aponta para esta assinatura;
          2. metadata[user_id] gravado na assinatura pelo checkout;
          3. client_reference_id do checkout (user_hint);
          4. o registro com o mesmo customer.
        Fontes que discordam entre si são um sinal de adulteração ou de erro
        de operação no dashboard: a assinatura é ignorada e o caso logado.
        """
        sub_id = str(sub.get("id") or "")
        meta = str(((sub.get("metadata") or {}).get("user_id")) or "") or None
        pelo_registro = self._user_por_coluna("stripe_subscription_id", sub_id)
        customer = self._id_de(sub.get("customer"))
        pelo_customer = self._user_por_coluna("stripe_customer_id", customer) if customer else None

        declarados = {u for u in (meta, user_hint) if u}
        if len(declarados) > 1:
            logger.error("[Billing] assinatura %s: metadata=%r e checkout=%r discordam", sub_id, meta, user_hint)
            return None
        if pelo_registro and declarados and pelo_registro not in declarados:
            logger.error("[Billing] assinatura %s já vinculada a outro usuário — ignorada", sub_id)
            return None
        return pelo_registro or meta or user_hint or pelo_customer

    @staticmethod
    def _id_de(valor) -> str | None:
        if isinstance(valor, dict):
            valor = valor.get("id")
        return str(valor) if valor else None

    # ── helpers ─────────────────────────────────────────────────────

    def _plan_from_subscription(self, sub: dict) -> str | None:
        """Plano pelo(s) price(s) da assinatura; com mais de um item, o maior."""
        items = ((sub.get("items") or {}).get("data")) or []
        planos = [self.stripe.plan_for_price(item.get("price") or {}) for item in items]
        planos = [p for p in planos if p]
        if not planos:
            return None
        return PLAN_TOTAL if any(plan_satisfies(p, PLAN_TOTAL) for p in planos) else PLAN_PRO

    @staticmethod
    def _period_end(sub: dict):
        """Fim do período pago: no topo da assinatura (API até 2025-03) ou
        nos itens (API basil em diante)."""
        candidatos = [sub.get("current_period_end")]
        for item in ((sub.get("items") or {}).get("data")) or []:
            candidatos.append(item.get("current_period_end"))
        valores = []
        for raw in candidatos:
            try:
                if raw:
                    valores.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not valores:
            return None
        try:
            return datetime.fromtimestamp(max(valores), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _user_por_coluna(coluna: str, valor: str | None) -> str | None:
        if not valor:
            return None
        try:
            from app.billing.models_orm import UserSubscription
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                row = (
                    db.query(UserSubscription)
                    .filter(getattr(UserSubscription, coluna) == valor)
                    .first()
                )
                return row.user_id if row else None
        except Exception as exc:
            logger.warning("[Billing] busca por %s falhou: %s", coluna, exc)
            return None

    @staticmethod
    def _ja_processado(event_id: str) -> bool:
        try:
            from app.billing.models_orm import BillingWebhookEvent
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                return db.get(BillingWebhookEvent, event_id) is not None
        except Exception as exc:
            # Sem a tabela (migração não aplicada) o processamento continua:
            # a sincronização é idempotente.
            logger.warning("[Billing] checagem de evento repetido indisponível: %s", exc)
            return False

    @staticmethod
    def _marcar_processado(event_id: str, event_type: str) -> None:
        try:
            from sqlalchemy.exc import IntegrityError

            from app.billing.models_orm import BillingWebhookEvent
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                db.add(BillingWebhookEvent(
                    event_id=event_id, event_type=event_type[:80],
                    processed_at=datetime.now(timezone.utc),
                ))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()  # outra entrega do mesmo evento chegou antes
        except Exception as exc:
            logger.warning("[Billing] registro do evento %s falhou: %s", event_id, exc)

    @staticmethod
    def _upsert(*, user_id: str, event_id: str, plan: str, status: str,
                customer_id, subscription_id, period_end, cancel_at_end: bool) -> None:
        from app.billing.models_orm import UserSubscription
        from app.core.database import SessionLocal

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            record = db.get(UserSubscription, user_id)
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


__all__ = ["BillingService", "AssinaturaJaAtiva", "CheckoutDeOutroUsuario", "EVENTOS_TRATADOS"]
