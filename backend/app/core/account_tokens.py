"""
app/core/account_tokens.py — Emissão e consumo de tokens de conta.

Fluxos: reset de senha e verificação de e-mail.

Propriedades de segurança:
  - token = secrets.token_urlsafe(48) (~64 chars, 288 bits) — só o SHA-256
    vai para o banco; o plaintext existe apenas no e-mail do usuário;
  - uso único: consume() marca used_at atomicamente; segunda tentativa falha;
  - expiração: password_reset 60min, email_verify 48h;
  - emitir um token novo invalida os anteriores não usados do mesmo
    usuário+propósito (o link mais recente é o único válido).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_EMAIL_VERIFY = "email_verify"

_TTL_MINUTES = {
    PURPOSE_PASSWORD_RESET: 60,
    PURPOSE_EMAIL_VERIFY: 48 * 60,
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(user_id: str, purpose: str) -> str:
    """Gera um token novo (invalidando anteriores do mesmo propósito) e
    retorna o PLAINTEXT — o chamador envia por e-mail e nunca loga."""
    from app.core.database import SessionLocal
    from app.core.models.auth_token import AuthToken

    ttl = _TTL_MINUTES.get(purpose)
    if ttl is None:
        raise ValueError(f"Propósito desconhecido: {purpose}")

    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        # Invalida tokens anteriores não usados (o link novo é o único válido)
        db.query(AuthToken).filter(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        ).update({AuthToken.used_at: now}, synchronize_session=False)

        db.add(AuthToken(
            token_hash=_hash(token),
            user_id=user_id,
            purpose=purpose,
            expires_at=now + timedelta(minutes=ttl),
            created_at=now,
        ))
        db.commit()

    return token


def consume_token(token: str, purpose: str) -> str | None:
    """Valida e consome o token (uso único). Retorna user_id ou None —
    nunca detalha o motivo da falha (evita oráculo de estado do token)."""
    if not token or len(token) < 20:
        return None

    from app.core.database import SessionLocal
    from app.core.models.auth_token import AuthToken

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        record = db.get(AuthToken, _hash(token))
        if record is None or record.purpose != purpose or record.used_at is not None:
            return None
        expires = record.expires_at
        if expires is not None and expires.tzinfo is None:
            # SQLite devolve naive — trata como UTC
            expires = expires.replace(tzinfo=timezone.utc)
        if expires is not None and expires < now:
            return None
        record.used_at = now
        db.commit()
        return record.user_id


__all__ = [
    "issue_token", "consume_token",
    "PURPOSE_PASSWORD_RESET", "PURPOSE_EMAIL_VERIFY",
]
