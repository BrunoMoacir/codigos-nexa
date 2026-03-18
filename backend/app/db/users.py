import logging
from typing import Optional, Dict, Any
import uuid
from sqlalchemy.orm import Session
from app.models.user import User

logger = logging.getLogger(__name__)

def get_user_by_email(db: Session, email: str) -> Optional[Dict[str, Any]]:
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return {
                "user_id": user.user_id,
                "email": user.email,
                "hashed_password": user.hashed_password,
                "full_name": user.full_name
            }
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuario: {e}")
        return None

def create_user(db: Session, email: str, hashed_password: str, full_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        user_id = str(uuid.uuid4())
        db_user = User(
            user_id=user_id,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {
            "user_id": db_user.user_id,
            "email": db_user.email,
            "full_name": db_user.full_name
        }
    except Exception as e:
        logger.error(f"Erro ao criar usuario: {e}")
        db.rollback()
        return None
