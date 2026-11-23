"""
app/notifications/push_router.py — Inscrições Web Push (PWA, R1.d)

Endpoints:
  GET    /push/vapid-public-key        — chave pública para o pushManager
  POST   /push/subscribe/{user_id}     — registra a inscrição do navegador
  DELETE /push/subscribe/{user_id}     — revoga a inscrição
  GET    /push/status/{user_id}        — canal configurado? usuário inscrito?
  POST   /push/devices/{user_id}       — app nativo: registra o token FCM do aparelho
  DELETE /push/devices/{user_id}       — app nativo: remove o aparelho (logout)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["Web Push (PWA)"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """Formato padrão de PushSubscription.toJSON() do navegador."""
    endpoint: str = Field(..., min_length=10, max_length=1024)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def _endpoint_de_servico_de_push(cls, valor: str) -> str:
        # o servidor faz POST neste endereço: só serviços de push conhecidos (anti-SSRF)
        from app.core.notifications.push_sender import endpoint_permitido

        if not endpoint_permitido(valor):
            raise ValueError("endpoint de push não reconhecido")
        return valor


class AparelhoIn(BaseModel):
    """Token FCM do app nativo (Android/iOS)."""
    token: str = Field(..., min_length=20, max_length=512, pattern=r"^[A-Za-z0-9_:\-.]+$")
    platform: Literal["android", "ios"]
    app_version: Optional[str] = Field(default=None, max_length=40)


class RemoverAparelhoIn(BaseModel):
    token: Optional[str] = Field(default=None, max_length=512)


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


@router.post("/devices/{user_id}")
def registrar_aparelho(body: AparelhoIn, user_id: str = Depends(require_owner)) -> dict:
    """App nativo: grava o token FCM. Se o aparelho era de outra conta, passa para esta."""
    from app.core.notifications import fcm_sender

    try:
        fcm_sender.registrar_aparelho(user_id, body.token, body.platform, body.app_version)
    except Exception as exc:
        logger.warning("[Push] registro de aparelho falhou user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Falha ao registrar o aparelho.")
    return {"ok": True, "configured": fcm_sender.is_configured()}


@router.delete("/devices/{user_id}")
def remover_aparelho(body: RemoverAparelhoIn, user_id: str = Depends(require_owner)) -> dict:
    """Logout no app nativo: o aparelho para de receber os alertas desta conta."""
    from app.core.notifications import fcm_sender

    return {"removed": fcm_sender.remover_aparelho(user_id, body.token)}
