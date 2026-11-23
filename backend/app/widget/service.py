"""
app/widget/service.py — emissão, validação e revogação dos tokens do widget.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PREFIXO = "hwt_"
VALIDADE = timedelta(days=90)
# last_used_at só é regravado de hora em hora: o widget consulta a cada 15 min
_GRAVA_USO_A_CADA = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def emitir(user_id: str, device_id: str) -> tuple[str, datetime]:
    """Token novo para o aparelho; o anterior do MESMO aparelho é revogado."""
    from app.core.database import SessionLocal
    from app.widget.models_orm import WidgetToken

    agora = datetime.now(timezone.utc)
    token = PREFIXO + secrets.token_urlsafe(32)
    expira = agora + VALIDADE
    with SessionLocal() as db:
        (
            db.query(WidgetToken)
            .filter(WidgetToken.user_id == user_id, WidgetToken.device_id == device_id,
                    WidgetToken.revoked_at.is_(None))
            .update({WidgetToken.revoked_at: agora}, synchronize_session=False)
        )
        db.add(WidgetToken(
            id=str(uuid.uuid4()), user_id=user_id, device_id=device_id,
            token_hash=_hash(token), created_at=agora, expires_at=expira,
        ))
        db.commit()
    return token, expira


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _conta_aceita(db, user_id: str, emitido_em: datetime) -> bool:
    """
    A conta ainda existe e está ativa, e o token é posterior ao último corte
    de sessão (reset de senha, "sair de todos os aparelhos").

    É a segunda trava. A primeira é a revogação explícita nesses fluxos. Esta
    garante que nenhum caminho que corte as sessões e esqueça o widget deixe um
    token de 90 dias de pé, pela mesma regra que `get_current_user` aplica ao
    JWT.
    """
    from app.core.db.users import get_user_by_id

    conta = get_user_by_id(db, user_id)
    if conta is None or not conta.get("is_active", True):
        return False
    corte = conta.get("sessions_valid_from")
    return corte is None or _utc(emitido_em) >= _utc(corte)


def validar(token: str | None) -> str | None:
    """Dono do token, ou None se ausente, desconhecido, revogado ou vencido."""
    if not token or not token.startswith(PREFIXO) or len(token) > 200:
        return None
    from app.core.database import SessionLocal
    from app.widget.models_orm import WidgetToken

    agora = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            row = db.query(WidgetToken).filter(WidgetToken.token_hash == _hash(token)).first()
            if row is None or row.revoked_at is not None:
                return None
            expira = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if expira <= agora:
                return None
            if not _conta_aceita(db, row.user_id, row.created_at):
                return None
            ultimo = row.last_used_at
            if ultimo is not None and ultimo.tzinfo is None:
                ultimo = ultimo.replace(tzinfo=timezone.utc)
            if ultimo is None or agora - ultimo > _GRAVA_USO_A_CADA:
                row.last_used_at = agora
                db.commit()
            return row.user_id
    except Exception as exc:
        logger.warning("[Widget] validação indisponível: %s", exc)
        return None


def revogar(user_id: str, device_id: str | None = None) -> int:
    """Revoga os tokens do aparelho (ou de TODOS os aparelhos, sem device_id)."""
    from app.core.database import SessionLocal
    from app.widget.models_orm import WidgetToken

    agora = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            q = db.query(WidgetToken).filter(WidgetToken.user_id == user_id, WidgetToken.revoked_at.is_(None))
            if device_id:
                q = q.filter(WidgetToken.device_id == device_id)
            n = q.update({WidgetToken.revoked_at: agora}, synchronize_session=False)
            db.commit()
            return int(n)
    except Exception as exc:
        logger.warning("[Widget] revogação falhou user=%s: %s", user_id, exc)
        return 0
