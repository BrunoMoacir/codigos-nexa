"""
app/settings/router.py — Preferências do usuário (user_settings)

GET  /api/v1/settings/{user_id}  — lê preferências (retorna defaults se linha não existe)
PUT  /api/v1/settings/{user_id}  — cria ou atualiza preferências (upsert)

Campos gerenciados:
  notification_channels   — ["email"] | ["in_app"] | ["email", "in_app"] | ["push"]
  notification_frequency  — "realtime" | "daily" | "weekly" | "off"
  digest_time             — "HH:MM" (horário do digest diário)
  subscription_status     — "active" | "paused" | "cancelled"
  paused_until            — timestamp UTC (quando subscription_status = "paused")
"""

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings (user_settings)"])

# ── Defaults usados quando a linha não existe ────────────────────────
_DEFAULT_CHANNELS: list[str] = ["in_app"]
_DEFAULT_FREQUENCY: str = "daily"
_DEFAULT_DIGEST_TIME: str = "07:00"
_DEFAULT_STATUS: str = "active"

Channel = Literal["email", "in_app", "push"]
Frequency = Literal["realtime", "daily", "weekly", "off"]
SubscriptionStatus = Literal["active", "paused", "cancelled"]


# ── Schemas ──────────────────────────────────────────────────────────

class UserSettingsResponse(BaseModel):
    user_id: str
    notification_channels: list[str]
    notification_frequency: str
    digest_time: str
    subscription_status: str
    paused_until: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_default: bool  # True quando a linha não existe e estamos retornando defaults


class UserSettingsUpdate(BaseModel):
    notification_channels: Optional[list[Channel]] = None
    notification_frequency: Optional[Frequency] = None
    digest_time: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None
    paused_until: Optional[datetime] = None

    @field_validator("digest_time")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            parts = v.split(":")
            assert len(parts) == 2
            h, m = int(parts[0]), int(parts[1])
            assert 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            raise ValueError("digest_time deve estar no formato HH:MM (ex: 07:00)")
        return v

    @field_validator("paused_until")
    @classmethod
    def validate_paused_until(cls, v: datetime | None) -> datetime | None:
        if v is not None and v <= datetime.now(timezone.utc):
            raise ValueError("paused_until deve ser uma data futura")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserSettingsResponse)
def get_settings(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    """
    Retorna as preferências do usuário.
    Quando não há linha em user_settings, retorna os valores padrão
    sem criar registro (criação acontece no primeiro PUT ou no cadastro).
    """
    try:
        from sqlalchemy import text

        row = db.execute(
            text(
                "SELECT notification_channels, notification_frequency, digest_time,"
                "       subscription_status, paused_until, updated_at"
                " FROM user_settings WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchone()
    except Exception as exc:
        logger.error("[settings] get_settings user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao buscar preferências.")

    if row is None:
        return UserSettingsResponse(
            user_id=user_id,
            notification_channels=_DEFAULT_CHANNELS,
            notification_frequency=_DEFAULT_FREQUENCY,
            digest_time=_DEFAULT_DIGEST_TIME,
            subscription_status=_DEFAULT_STATUS,
            paused_until=None,
            updated_at=None,
            is_default=True,
        )

    channels_raw = row[0]
    try:
        channels = json.loads(channels_raw) if channels_raw else _DEFAULT_CHANNELS
    except (ValueError, TypeError):
        channels = _DEFAULT_CHANNELS

    return UserSettingsResponse(
        user_id=user_id,
        notification_channels=channels,
        notification_frequency=row[1] or _DEFAULT_FREQUENCY,
        digest_time=row[2] or _DEFAULT_DIGEST_TIME,
        subscription_status=row[3] or _DEFAULT_STATUS,
        paused_until=row[4],
        updated_at=row[5],
        is_default=False,
    )


@router.put("/{user_id}", response_model=UserSettingsResponse)
def update_settings(
    body: UserSettingsUpdate,
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    """
    Cria ou atualiza as preferências do usuário (upsert).

    Apenas os campos presentes no body são atualizados.
    Campos omitidos mantêm o valor atual (ou o default se a linha ainda não existia).

    **Exemplos de uso:**
    - Pausar notificações: `{"subscription_status": "paused", "paused_until": "2026-07-30T00:00:00Z"}`
    - Migrar para email: `{"notification_channels": ["email", "in_app"]}`
    - Desligar digest: `{"notification_frequency": "off"}`
    """
    now = datetime.now(timezone.utc)

    try:
        from sqlalchemy import text

        # Lê o estado atual (ou usa defaults)
        existing = db.execute(
            text(
                "SELECT notification_channels, notification_frequency, digest_time,"
                "       subscription_status, paused_until"
                " FROM user_settings WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchone()
    except Exception as exc:
        logger.error("[settings] update_settings read user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao ler preferências atuais.")

    # Merge: valor do body > valor existente > default
    if existing:
        current_channels = _parse_channels(existing[0])
        current_freq = existing[1] or _DEFAULT_FREQUENCY
        current_time = existing[2] or _DEFAULT_DIGEST_TIME
        current_status = existing[3] or _DEFAULT_STATUS
        current_paused_until = existing[4]
    else:
        current_channels = list(_DEFAULT_CHANNELS)
        current_freq = _DEFAULT_FREQUENCY
        current_time = _DEFAULT_DIGEST_TIME
        current_status = _DEFAULT_STATUS
        current_paused_until = None

    new_channels = body.notification_channels if body.notification_channels is not None else current_channels
    new_freq = body.notification_frequency if body.notification_frequency is not None else current_freq
    new_time = body.digest_time if body.digest_time is not None else current_time
    new_status = body.subscription_status if body.subscription_status is not None else current_status
    new_paused_until = body.paused_until if body.paused_until is not None else (
        None if new_status != "paused" else current_paused_until
    )

    # Se saiu de paused → limpa paused_until automaticamente
    if new_status != "paused":
        new_paused_until = None

    try:
        from sqlalchemy import text

        db.execute(
            text(
                "INSERT INTO user_settings"
                "   (user_id, notification_channels, notification_frequency,"
                "    digest_time, subscription_status, paused_until, updated_at)"
                " VALUES (:uid, :ch, :freq, :dt, :st, :pu, :now)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                "   notification_channels  = EXCLUDED.notification_channels,"
                "   notification_frequency = EXCLUDED.notification_frequency,"
                "   digest_time            = EXCLUDED.digest_time,"
                "   subscription_status    = EXCLUDED.subscription_status,"
                "   paused_until           = EXCLUDED.paused_until,"
                "   updated_at             = EXCLUDED.updated_at"
            ),
            {
                "uid":  user_id,
                "ch":   json.dumps(new_channels),
                "freq": new_freq,
                "dt":   new_time,
                "st":   new_status,
                "pu":   new_paused_until,
                "now":  now,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("[settings] update_settings write user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao salvar preferências.")

    logger.info("[settings] user=%s atualizado: freq=%s status=%s", user_id, new_freq, new_status)

    return UserSettingsResponse(
        user_id=user_id,
        notification_channels=new_channels,
        notification_frequency=new_freq,
        digest_time=new_time,
        subscription_status=new_status,
        paused_until=new_paused_until,
        updated_at=now,
        is_default=False,
    )


# ── Helper interno (reutilizado em auth.py) ──────────────────────────

def create_default_settings(user_id: str, db: Session) -> None:
    """
    Cria linha de settings com valores padrão para um usuário novo.
    Chamado pelo endpoint de registro. Falha silenciosamente.
    """
    try:
        from sqlalchemy import text

        db.execute(
            text(
                "INSERT INTO user_settings"
                "   (user_id, notification_channels, notification_frequency,"
                "    digest_time, subscription_status, updated_at)"
                " VALUES (:uid, :ch, :freq, :dt, :st, :now)"
                " ON CONFLICT (user_id) DO NOTHING"
            ),
            {
                "uid":  user_id,
                "ch":   json.dumps(_DEFAULT_CHANNELS),
                "freq": _DEFAULT_FREQUENCY,
                "dt":   _DEFAULT_DIGEST_TIME,
                "st":   _DEFAULT_STATUS,
                "now":  datetime.now(timezone.utc),
            },
        )
        db.commit()
        logger.debug("[settings] defaults criados para user=%s", user_id)
    except Exception as exc:
        logger.warning("[settings] create_default_settings user=%s: %s", user_id, exc)


def _parse_channels(raw: str | None) -> list[str]:
    try:
        return json.loads(raw) if raw else list(_DEFAULT_CHANNELS)
    except (ValueError, TypeError):
        return list(_DEFAULT_CHANNELS)
