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
        }
    except Exception as e:
        logger.error(f"DuckDB fallback get_user_by_email falhou: {e}")
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
        logger.error(f"Postgres indisponível, caindo para DuckDB (get_user_by_email): {e}")
        return _get_user_by_email_duckdb(email)

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
        logger.error(f"DuckDB fallback create_user falhou: {e}")
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
        logger.error(f"Postgres indisponível, caindo para DuckDB (create_user): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return _create_user_duckdb(email=email, hashed_password=hashed_password, full_name=full_name)
