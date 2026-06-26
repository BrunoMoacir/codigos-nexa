"""
app/core/notifications/email_sender.py — Adapter de envio de email.

Suporta dois backends, configurados via variáveis de ambiente:
  1. SendGrid (recomendado para produção)  — SENDGRID_API_KEY definido
  2. SMTP (dev / self-hosted)              — SMTP_HOST + SMTP_USER + SMTP_PASSWORD

Se nenhum backend estiver configurado, o envio é silenciosamente ignorado
(log em WARNING). Isso garante que o código funciona em dev sem config de email.

Uso:
    from app.core.notifications.email_sender import send_email
    ok = send_email(to="user@email.com", subject="Olá", html_body="<p>Teste</p>")
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_via_sendgrid(to: str, subject: str, html_body: str) -> bool:
    """Envia via SendGrid HTTP API v3. Não requer SDK externo."""
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("[EmailSender] SendGrid → %s (status %d)", to, resp.status_code)
        return True
    except Exception as exc:
        logger.error("[EmailSender] Falha SendGrid → %s: %s", to, exc)
        return False


def _send_via_smtp(to: str, subject: str, html_body: str) -> bool:
    """Envia via SMTP usando smtplib (nativo Python)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if settings.SMTP_PORT != 465:
                server.starttls()
                server.ehlo()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, [to], msg.as_string())
        logger.info("[EmailSender] SMTP → %s", to)
        return True
    except Exception as exc:
        logger.error("[EmailSender] Falha SMTP → %s: %s", to, exc)
        return False


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Envia um email HTML. Escolhe backend automaticamente:
      SendGrid se SENDGRID_API_KEY estiver definido, senão SMTP, senão no-op.

    Returns:
        True se enviado com sucesso, False em caso de erro ou sem configuração.
    """
    if settings.SENDGRID_API_KEY:
        return _send_via_sendgrid(to, subject, html_body)

    if settings.SMTP_HOST:
        return _send_via_smtp(to, subject, html_body)

    logger.warning(
        "[EmailSender] Nenhum backend configurado (SENDGRID_API_KEY e SMTP_HOST vazios). "
        "Email para %s ignorado: %s",
        to,
        subject,
    )
    return False
