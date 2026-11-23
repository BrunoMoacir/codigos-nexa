# app/notifications/models_orm.py — aparelhos com push nativo (FCM)
from sqlalchemy import Column, DateTime, String

from app.core.database import Base


class PushDevice(Base):
    """
    Token FCM de um aparelho com o app nativo (Android/iOS).

    O token identifica o APARELHO, não a pessoa: se outra conta entrar no
    mesmo celular, o token passa para ela (e sai da anterior) — senão os
    alertas financeiros de quem saiu continuariam chegando ali.
    """

    __tablename__ = "push_devices"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    token = Column(String(512), nullable=False, unique=True)
    platform = Column(String(10), nullable=False)  # android | ios
    app_version = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
