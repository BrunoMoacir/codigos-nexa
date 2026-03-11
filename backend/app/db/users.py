import duckdb
import logging
from typing import Optional, Dict, Any
import uuid

from app.db.queries import get_connection

logger = logging.getLogger(__name__)

def _ensure_users_table(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         VARCHAR PRIMARY KEY,
            email           VARCHAR UNIQUE NOT NULL,
            hashed_password VARCHAR NOT NULL,
            full_name       VARCHAR,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    con = get_connection()
    try:
        _ensure_users_table(con)
        res = con.execute("SELECT user_id, email, hashed_password, full_name FROM users WHERE email = ?", [email]).fetchone()
        if res:
            return {
                "user_id": res[0],
                "email": res[1],
                "hashed_password": res[2],
                "full_name": res[3]
            }
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuario: {e}")
        return None
    finally:
        con.close()

def create_user(email: str, hashed_password: str, full_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    con = get_connection()
    try:
        _ensure_users_table(con)
        user_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO users (user_id, email, hashed_password, full_name) VALUES (?, ?, ?, ?)",
            [user_id, email, hashed_password, full_name]
        )
        return {
            "user_id": user_id,
            "email": email,
            "full_name": full_name
        }
    except Exception as e:
        logger.error(f"Erro ao criar usuario: {e}")
        return None
    finally:
        con.close()
