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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _log_delivery(
    user_id: str,
    notification_id: str,
    channel: Channel,
    result: "DeliveryResult",
) -> None:
    """
    Persiste tentativa de entrega em notification_delivery_log.
    Falha silenciosamente — nunca deve bloquear a entrega em si.
    """
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        status = "sent" if result.success else "failed"

        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO notification_delivery_log"
                    " (id, user_id, notification_id, channel, status,"
                    "  attempts, last_error, sent_at)"
                    " VALUES (:id, :uid, :nid, :ch, :st, 1, :err, :sent_at)"
                ),
                {
                    "id":      str(uuid.uuid4()),
                    "uid":     user_id,
                    "nid":     notification_id,
                    "ch":      channel,
                    "st":      status,
                    "err":     result.error,
                    "sent_at": now if result.success else None,
                },
            )
            db.commit()
    except Exception as exc:
        logger.debug("[DeliveryService] _log_delivery falhou: %s", exc)


def deliver(
    user_id: str,
    subject: str,
    html_body: str,
    notification_type: str = "generic",
    notification_id: str = "",
) -> list[DeliveryResult]:
    """
    Entrega uma notificação ao usuário pelos canais configurados e
    persiste cada tentativa em notification_delivery_log.

    Args:
        user_id:           ID do usuário destinatário.
        subject:           Assunto / título da notificação.
        html_body:         Corpo em HTML (para email) ou texto simples (para in_app).
        notification_type: Tipo para logging (ex: "daily_digest", "tarifa_aumento").
        notification_id:   ID da notificação de origem (para rastreamento). Se vazio,
                           gera um UUID automaticamente.

    Returns:
        Lista de DeliveryResult — um por canal tentado.
    """
    nid = notification_id or str(uuid.uuid4())
    channels = _get_user_channels(user_id)
    results: list[DeliveryResult] = []

    for channel in channels:
        if channel == "email":
            email = _get_user_email(user_id)
            if not email:
                r = DeliveryResult(channel="email", success=False, error="email não encontrado")
                results.append(r)
                _log_delivery(user_id, nid, "email", r)
                continue
            ok = send_email(to=email, subject=subject, html_body=html_body)
            r = DeliveryResult(channel="email", success=ok)
            results.append(r)
            _log_delivery(user_id, nid, "email", r)

        elif channel == "in_app":
            logger.debug("[DeliveryService] in_app | user=%s type=%s", user_id, notification_type)
            r = DeliveryResult(channel="in_app", success=True)
            results.append(r)
            _log_delivery(user_id, nid, "in_app", r)

        elif channel == "push":
            logger.info("[DeliveryService] push ainda não implementado | user=%s", user_id)
            r = DeliveryResult(channel="push", success=False, error="não implementado")
            results.append(r)
            _log_delivery(user_id, nid, "push", r)

    if not results:
        r = DeliveryResult(channel="in_app", success=True)
        results.append(r)
        _log_delivery(user_id, nid, "in_app", r)

    return results
