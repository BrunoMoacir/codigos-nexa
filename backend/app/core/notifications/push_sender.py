"""
app/core/notifications/push_sender.py — Canal Web Push (PWA, R1.d)

Envia notificações push para as inscrições (push_subscriptions) do
usuário via protocolo Web Push com VAPID (pywebpush).

Comportamento:
  - Sem VAPID configurado ou sem pywebpush instalado → canal desativado
    (is_configured() = False), tudo falha aberto.
  - Endpoint que responde 404/410 (inscrição expirada/revogada pelo
    navegador) é marcado revoked_at e não recebe mais tentativas.
  - Payload JSON: {title, body, url, tag} — interpretado pelo service
    worker do frontend (frontend-react/public/sw.js).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class PushSubscription:
    id: str
    endpoint: str
    p256dh: str
    auth: str


def is_configured() -> bool:
    """True quando há chaves VAPID e a lib pywebpush está disponível."""
    from app.core.config import settings

    if not (settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY):
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


# ── CRUD de inscrições ───────────────────────────────────────────────

def save_subscription(
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
) -> bool:
    """Cria (ou reativa) uma inscrição. Idempotente por (user, endpoint)."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            updated = db.execute(
                text(
                    "UPDATE push_subscriptions"
                    " SET p256dh = :p, auth = :a, revoked_at = NULL"
                    " WHERE user_id = :uid AND endpoint = :ep"
                ),
                {"p": p256dh, "a": auth, "uid": user_id, "ep": endpoint},
            )
            if updated.rowcount == 0:
                db.execute(
                    text(
                        "INSERT INTO push_subscriptions"
                        " (id, user_id, endpoint, p256dh, auth, user_agent, created_at)"
                        " VALUES (:id, :uid, :ep, :p, :a, :ua, :now)"
                    ),
                    {
                        "id": str(uuid.uuid4()), "uid": user_id, "ep": endpoint,
                        "p": p256dh, "a": auth, "ua": user_agent[:255], "now": now,
                    },
                )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("[PushSender] save_subscription user=%s: %s", user_id, exc)
        return False


def remove_subscription(user_id: str, endpoint: str) -> bool:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "UPDATE push_subscriptions SET revoked_at = :now"
                    " WHERE user_id = :uid AND endpoint = :ep"
                ),
                {"now": datetime.now(timezone.utc), "uid": user_id, "ep": endpoint},
            )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("[PushSender] remove_subscription user=%s: %s", user_id, exc)
        return False


def get_active_subscriptions(user_id: str) -> list[PushSubscription]:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT id, endpoint, p256dh, auth FROM push_subscriptions"
                    " WHERE user_id = :uid AND revoked_at IS NULL"
                ),
                {"uid": user_id},
            ).fetchall()
        return [PushSubscription(id=r[0], endpoint=r[1], p256dh=r[2], auth=r[3]) for r in rows]
    except Exception as exc:
        logger.debug("[PushSender] get_active_subscriptions user=%s: %s", user_id, exc)
        return []


def has_active_subscription(user_id: str) -> bool:
    return bool(get_active_subscriptions(user_id))


# ── Envio ────────────────────────────────────────────────────────────

def send_to_user(
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "",
) -> tuple[int, int]:
    """
    Envia push para todas as inscrições ativas do usuário.

    Returns:
        (enviados, falhados)
    """
    if not is_configured():
        return 0, 0

    subscriptions = get_active_subscriptions(user_id)
    if not subscriptions:
        return 0, 0

    from app.core.config import settings
    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag},
        ensure_ascii=False,
    )

    sent = failed = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
                ttl=6 * 3600,   # o alerta perde valor depois de algumas horas
            )
            sent += 1
            _mark_success(sub.id)
        except WebPushException as exc:
            failed += 1
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                # inscrição morta no push service — nunca mais tentar
                _revoke(sub.id)
                logger.info("[PushSender] inscrição %s revogada (HTTP %s)", sub.id, status)
            else:
                logger.warning("[PushSender] falha push sub=%s: %s", sub.id, exc)
        except Exception as exc:
            failed += 1
            logger.warning("[PushSender] erro inesperado sub=%s: %s", sub.id, exc)

    return sent, failed


def _mark_success(subscription_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text("UPDATE push_subscriptions SET last_success_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": subscription_id},
            )
            db.commit()
    except Exception:
        pass


def _revoke(subscription_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text("UPDATE push_subscriptions SET revoked_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": subscription_id},
            )
            db.commit()
    except Exception:
        pass


__all__ = [
    "PushSubscription",
    "get_active_subscriptions",
    "has_active_subscription",
    "is_configured",
    "remove_subscription",
    "save_subscription",
    "send_to_user",
]
