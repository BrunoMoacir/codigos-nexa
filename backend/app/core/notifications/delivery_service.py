"""
app/core/notifications/delivery_service.py — Orquestra a entrega de notificações.

Responsabilidade:
  Dado um user_id e uma notificação, decide qual canal usar e efetua a entrega.

Canais suportados:
  "email"   — via email_sender (SendGrid ou SMTP)
  "in_app"  — notificação armazenada; o usuário lê ao abrir o app (padrão)
  "push"    — futuro: Firebase Cloud Messaging (quando existir app mobile)

Preferências de canal:
  Consultadas na tabela user_settings (criada no item 2.x).
  Enquanto a tabela não existir, usa fallback: email se configurado, senão in_app.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from app.core.notifications.email_sender import send_email

logger = logging.getLogger(__name__)

Channel = Literal["email", "in_app", "push"]


@dataclass
class DeliveryResult:
    channel: Channel
    success: bool
    error: str | None = None


def _get_user_channels(user_id: str) -> list[Channel]:
    """
    Retorna os canais ativos para o usuário.
    Consulta user_settings quando disponível; fallback para ["in_app"].
    """
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text("SELECT notification_channels FROM user_settings WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
            if row and row[0]:
                import json
                channels = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                return [c for c in channels if c in ("email", "in_app", "push")]
    except Exception:
        # Tabela ainda não existe (item 2.x) ou erro de conexão — usa fallback
        pass

    from app.core.config import settings
    if settings.SENDGRID_API_KEY or settings.SMTP_HOST:
        return ["email"]
    return ["in_app"]


def _get_user_email(user_id: str) -> str | None:
    """Busca o email do usuário na tabela users."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text("SELECT email FROM users WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("[DeliveryService] Não foi possível buscar email do user %s: %s", user_id, exc)
        return None


def deliver(
    user_id: str,
    subject: str,
    html_body: str,
    notification_type: str = "generic",
) -> list[DeliveryResult]:
    """
    Entrega uma notificação ao usuário pelos canais configurados.

    Args:
        user_id:           ID do usuário destinatário.
        subject:           Assunto / título da notificação.
        html_body:         Corpo em HTML (para email) ou texto simples (para in_app).
        notification_type: Tipo para logging (ex: "daily_digest", "tarifa_aumento").

    Returns:
        Lista de DeliveryResult — um por canal tentado.
    """
    channels = _get_user_channels(user_id)
    results: list[DeliveryResult] = []

    for channel in channels:
        if channel == "email":
            email = _get_user_email(user_id)
            if not email:
                results.append(DeliveryResult(channel="email", success=False, error="email não encontrado"))
                continue
            ok = send_email(to=email, subject=subject, html_body=html_body)
            results.append(DeliveryResult(channel="email", success=ok))

        elif channel == "in_app":
            # in_app: a notificação já está armazenada pelo ProactiveNotifier/NotificationEngine.
            # Aqui apenas registramos que foi "entregue" para fins de log.
            logger.debug("[DeliveryService] in_app | user=%s type=%s", user_id, notification_type)
            results.append(DeliveryResult(channel="in_app", success=True))

        elif channel == "push":
            # Futuro: FCM
            logger.info("[DeliveryService] push ainda não implementado | user=%s", user_id)
            results.append(DeliveryResult(channel="push", success=False, error="não implementado"))

    if not results:
        results.append(DeliveryResult(channel="in_app", success=True))

    return results
