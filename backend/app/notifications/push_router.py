"""
app/notifications/push_router.py — Inscrições Web Push (PWA, R1.d)

Endpoints:
  GET    /push/vapid-public-key        — chave pública para o pushManager
  POST   /push/subscribe/{user_id}     — registra a inscrição do navegador
  DELETE /push/subscribe/{user_id}     — revoga a inscrição
  GET    /push/status/{user_id}        — canal configurado? usuário inscrito?
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["Web Push (PWA)"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """Formato padrão de PushSubscription.toJSON() do navegador."""
    endpoint: str = Field(..., min_length=10)
    keys: PushKeys


@router.get("/vapid-public-key")
def get_vapid_public_key() -> dict:
    """Chave pública VAPID (base64url) para `pushManager.subscribe`."""
    from app.core.config import settings
    from app.core.notifications import push_sender

    return {
        "configured": push_sender.is_configured(),
        "public_key": settings.VAPID_PUBLIC_KEY,
    }


@router.post("/subscribe/{user_id}")
def subscribe(
    body: PushSubscriptionIn,
    request: Request,
    user_id: str = Depends(require_owner),
) -> dict:
    from app.core.notifications import push_sender

    ok = push_sender.save_subscription(
        user_id=user_id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent", ""),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao registrar inscrição push.")
    logger.info("[Push] inscrição registrada user=%s", user_id)
    return {"ok": True}


@router.delete("/subscribe/{user_id}")
def unsubscribe(
    body: PushSubscriptionIn,
    user_id: str = Depends(require_owner),
) -> dict:
    from app.core.notifications import push_sender

    push_sender.remove_subscription(user_id, body.endpoint)
    return {"ok": True}


@router.get("/status/{user_id}")
def push_status(user_id: str = Depends(require_owner)) -> dict:
    from app.core.notifications import push_sender

    return {
        "configured": push_sender.is_configured(),
        "subscribed": push_sender.has_active_subscription(user_id),
    }
