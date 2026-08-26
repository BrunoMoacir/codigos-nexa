import logging
from typing import Optional, Dict, Any
import uuid
from sqlalchemy.orm import Session
from app.core.models.user import User

logger = logging.getLogger(__name__)

def _get_user_by_email_duckdb(email: str) -> Optional[Dict[str, Any]]:
    try:
        from app.core.db.queries import get_connection

        con = get_connection()
        try:
            row = con.execute(
                "SELECT user_id, email, hashed_password, full_name FROM users WHERE email = ? LIMIT 1",
                [email],
            ).fetchone()
        finally:
            con.close()

        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "hashed_password": row[2],
            "full_name": row[3],
            "is_active": True,
        }
    except Exception as e:
        logger.error("DuckDB fallback get_user_by_email falhou: %s", e)
        return None


def _get_user_by_id_duckdb(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        from app.core.db.queries import get_connection

        con = get_connection()
        try:
            row = con.execute(
                "SELECT user_id, email, hashed_password, full_name FROM users WHERE user_id = ? LIMIT 1",
                [user_id],
            ).fetchone()
        finally:
            con.close()

        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "hashed_password": row[2],
            "full_name": row[3],
            "is_active": True,
        }
    except Exception as e:
        logger.error("DuckDB fallback get_user_by_id falhou: %s", e)
        return None


def get_user_by_email(db: Session, email: str) -> Optional[Dict[str, Any]]:
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return {
                "user_id": user.user_id,
                "email": user.email,
                "hashed_password": user.hashed_password,
                "full_name": user.full_name,
            }
        # Se não achou no Postgres, tenta DuckDB (para dev/demo)
        return _get_user_by_email_duckdb(email)
    except Exception as e:
        logger.error("Postgres indisponível, caindo para DuckDB (get_user_by_email): %s", e)
        return _get_user_by_email_duckdb(email)


def get_user_by_id(db: Session, user_id: str) -> Optional[Dict[str, Any]]:
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            return {
                "user_id": user.user_id,
                "email": user.email,
                "hashed_password": user.hashed_password,
                "full_name": user.full_name,
                "is_active": bool(getattr(user, "is_active", True)),
                "sessions_valid_from": getattr(user, "sessions_valid_from", None),
            }
        return _get_user_by_id_duckdb(user_id)
    except Exception as e:
        logger.error("Postgres indisponível, caindo para DuckDB (get_user_by_id): %s", e)
        return _get_user_by_id_duckdb(user_id)

def _create_user_duckdb(email: str, hashed_password: str, full_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        from datetime import datetime, timezone
        from app.core.db.queries import get_connection

        user_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        con = get_connection()
        try:
            con.execute(
                "INSERT INTO users (user_id, email, hashed_password, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
                [user_id, email, hashed_password, full_name, created_at],
            )
        finally:
            con.close()

        return {"user_id": user_id, "email": email, "full_name": full_name}
    except Exception as e:
        logger.error("DuckDB fallback create_user falhou: %s", e)
        return None


def create_user(db: Session, email: str, hashed_password: str, full_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        user_id = str(uuid.uuid4())
        db_user = User(
            user_id=user_id,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {
            "user_id": db_user.user_id,
            "email": db_user.email,
            "full_name": db_user.full_name,
        }
    except Exception as e:
        logger.error("Postgres indisponível, caindo para DuckDB (create_user): %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return _create_user_duckdb(email=email, hashed_password=hashed_password, full_name=full_name)


def update_user_password(db: Session, user_id: str, hashed_password: str) -> bool:
    """
    Atualiza a senha E derruba todas as sessões abertas.

    As duas coisas na MESMA transação, de propósito: trocar a senha sem cortar
    as sessões deixava um token roubado sobreviver ao reset — access por até 30
    min, refresh por até 14 DIAS. Quem troca a senha porque desconfia de invasão
    espera exatamente o contrário.

    `sessions_valid_from` é comparado com o claim `iat` de cada token em
    `security.sessao_invalidada`, sem custo extra por request.

    Retorna False se o usuário não existe.
    """
    from datetime import datetime, timezone

    try:
        rows = (
            db.query(User)
            .filter(User.user_id == user_id)
            .update(
                {
                    User.hashed_password: hashed_password,
                    User.sessions_valid_from: datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return rows > 0
    except Exception as e:
        logger.error("update_user_password falhou user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def encerrar_sessoes(db: Session, user_id: str) -> bool:
    """
    Invalida todo token já emitido para o usuário (corte de sessão).

    Usado pelo reset de senha e disponível para "sair de todos os
    dispositivos". Diferente da blacklist por `jti`, que revoga UM token e
    depende do Redis, este corte vive no banco e não tem fail-open.
    """
    from datetime import datetime, timezone

    try:
        rows = (
            db.query(User)
            .filter(User.user_id == user_id)
            .update(
                {User.sessions_valid_from: datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        db.commit()
        return rows > 0
    except Exception as e:
        logger.error("encerrar_sessoes falhou user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def mark_email_verified(db: Session, user_id: str) -> bool:
    """Marca o e-mail do usuário como verificado (fluxo de verificação)."""
    from datetime import datetime, timezone

    try:
        rows = (
            db.query(User)
            .filter(User.user_id == user_id)
            .update(
                {
                    User.email_verified: True,
                    User.email_verified_at: datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return rows > 0
    except Exception as e:
        logger.error("mark_email_verified falhou user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:
            pass
        return False
