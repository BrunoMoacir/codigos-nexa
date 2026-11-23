# app/billing/models.py — schemas Pydantic do billing
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class PlanOut(BaseModel):
    plan_id: str
    name: str
    price_brl_monthly: float
    tagline: str
    features: list[str]


class UsageOut(BaseModel):
    key: str
    used: int
    limit: int
    window: str
    description: str


class SubscriptionOut(BaseModel):
    user_id: str
    plan: str                       # plano efetivo (considera status)
    status: str
    cancel_at_period_end: bool = False
    current_period_end: Optional[datetime] = None
    usage: list[UsageOut] = []
    billing_enabled: bool           # False = Stripe não configurado neste ambiente
    enforcement_enabled: bool       # False = gating em modo observação (dark launch)


class CheckoutIn(BaseModel):
    plan: Literal["pro", "total"]


class CheckoutOut(BaseModel):
    checkout_url: str
    session_id: str


class PortalOut(BaseModel):
    portal_url: str


class ConfirmIn(BaseModel):
    """Volta do Checkout: o session_id que o Stripe pôs na success_url."""
    session_id: str


class ConfirmOut(BaseModel):
    plan: str                       # plano efetivo depois da sincronização
