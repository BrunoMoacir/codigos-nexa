# app/widget/models_orm.py — tokens de escopo restrito do widget nativo
from sqlalchemy import Column, DateTime, Index, String

from app.core.database import Base


class WidgetToken(Base):
    """
    Credencial do widget de tela inicial (Android/iOS).

    O widget roda fora do app, de 15 em 15 minutos. Dar a ele o refresh token
    da sessão era inviável: o refresh é de uso único, e o app e o widget
    rotacionando o mesmo token derrubariam a sessão um do outro. Este token só
    LÊ a margem do dia, vale 90 dias, é um por aparelho e é revogado no
    logout, no "sair de todos os aparelhos", no reset de senha e na exclusão
    da conta.

    Só o SHA-256 do token é guardado: um vazamento do banco não entrega
    credencial utilizável.
    """

    __tablename__ = "widget_tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    device_id = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_widget_tokens_user_device", "user_id", "device_id"),)
