# app/billing/models_orm.py — tabela de assinaturas
from sqlalchemy import Column, String, Boolean, DateTime, Index
from app.core.database import Base


class UserSubscription(Base):
    """
    Uma linha por usuário (user_id é PK): o plano vigente e o vínculo Stripe.

    status segue o vocabulário do Stripe: active, trialing, past_due,
    canceled, unpaid, incomplete. Plano efetivo = plan quando status em
    (active, trialing, past_due*); caso contrário, free.
    (*past_due mantém acesso por cortesia até o Stripe cancelar — evita
    cortar o usuário por falha transitória de cartão.)
    """

    __tablename__ = "user_subscriptions"

    user_id = Column(String(100), primary_key=True)
    plan = Column(String(20), nullable=False, default="free")
    status = Column(String(30), nullable=False, default="active")
    stripe_customer_id = Column(String(100), nullable=True, index=True)
    stripe_subscription_id = Column(String(100), nullable=True, index=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    # Idempotência de webhook: último event id processado para este usuário
    last_event_id = Column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_user_subscriptions_plan_status", "plan", "status"),
    )


class BillingWebhookEvent(Base):
    """
    Eventos do Stripe já processados (event id único). O Stripe reenvia o
    mesmo evento em retries e pode entregá-lo duas vezes; a última checagem
    por usuário (`last_event_id`) só pegava a repetição imediata — A, B, A
    reprocessava A.
    """

    __tablename__ = "billing_webhook_events"

    event_id = Column(String(100), primary_key=True)
    event_type = Column(String(80), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=False)
