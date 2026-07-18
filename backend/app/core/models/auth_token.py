# app/core/models/auth_token.py — tokens de conta (reset de senha / verificação)
from sqlalchemy import Column, String, DateTime, Index
from app.core.database import Base


class AuthToken(Base):
    """
    Token de uso único para fluxos de conta:
      purpose = "password_reset" | "email_verify"

    Só o SHA-256 do token é armazenado — vazamento da tabela não permite
    usar os tokens. O plaintext existe apenas no e-mail enviado ao usuário.
    """

    __tablename__ = "auth_tokens"

    token_hash = Column(String(64), primary_key=True)   # sha256 hex
    user_id = Column(String(100), nullable=False, index=True)
    purpose = Column(String(30), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_auth_tokens_user_purpose", "user_id", "purpose"),
    )
