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
        email=email,
        ip=ip,
        reason=reason,
        req=request_id,
        ts=_now(),
    ))


def log_register(user_id: str, email: str, ip: str, request_id: str | None = None) -> None:
    _audit.info(_fmt(
        event="AUTH_REGISTER",
        user=user_id,
        email=email,
        ip=ip,
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
