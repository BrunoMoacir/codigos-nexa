"""
app/core/audit.py — Audit logging estruturado.

Registra eventos de segurança e acesso a dados sensíveis em um logger
dedicado ("nexa.audit"), separado dos logs de aplicação.

Formato de cada entrada:
    AUDIT | <event_type> | user=<id> | ip=<addr> | <campos extras>

Para produção, redirecione o logger "nexa.audit" para um sink imutável
(CloudWatch, Elasticsearch, arquivo append-only) fora do alcance da app.
"""

import logging
from datetime import datetime, timezone
from typing import Any

_audit = logging.getLogger("nexa.audit")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt(**fields: Any) -> str:
    parts = " | ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    return f"AUDIT | {parts}"


def mask_email(email: str) -> str:
    """
    Mascara PII antes de logar (LGPD): 'gabriel@nexa.com' → 'g*****l@nexa.com'.

    Logs de auditoria são retidos por longos períodos e frequentemente
    exportados para sinks externos — email em claro neles é dado pessoal
    fora de controle. O mascarado continua útil para investigação
    (domínio + iniciais) sem expor o titular.
    """
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[0] + "*" if local else "*"
    else:
        masked_local = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked_local}@{domain}"


# ── Eventos de autenticação ────────────────────────────────────────────────

def log_login_success(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_LOGIN_SUCCESS",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


def log_login_failure(email: str, ip: str, reason: str, request_id: str | None = None) -> None:
    _audit.warning(_fmt(
        event="AUTH_LOGIN_FAILURE",
        email=mask_email(email),
        ip=ip,
        reason=reason,
        req=request_id,
        ts=_now(),
    ))


def log_register(user_id: str, email: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_REGISTER",
        user=user_id,
        email=mask_email(email),
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


# ── Eventos LGPD (direitos do titular) ─────────────────────────────────────

def log_privacy_export(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="PRIVACY_EXPORT",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


def log_privacy_deletion(
    user_id: str, ip: str, tables_purged: int, request_id: str | None = None
) -> None:
    _audit.warning(_fmt(
        event="PRIVACY_DELETION",
        user=user_id,
        ip=ip,
        tables=tables_purged,
        req=request_id,
        ts=_now(),
    ))


def log_logout(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_LOGOUT",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


def log_password_reset_requested(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_PASSWORD_RESET_REQUESTED",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


def log_password_reset_completed(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_PASSWORD_RESET_COMPLETED",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


def log_email_verified(user_id: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_EMAIL_VERIFIED",
        user=user_id,
        ip=ip,
        req=request_id,
        ts=_now(),
    ))


# ── Eventos de acesso a dados ──────────────────────────────────────────────

def log_data_access(
    user_id: str,
    endpoint: str,
    method: str,
    ip: str,
    status_code: int,
    request_id: str | None = None,
) -> None:
    _audit.info(_fmt(
        event="DATA_ACCESS",
        user=user_id,
        endpoint=endpoint,
        method=method,
        ip=ip,
        status=status_code,
        req=request_id,
        ts=_now(),
    ))
