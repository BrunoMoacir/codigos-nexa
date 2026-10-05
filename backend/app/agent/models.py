from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.sql import func
from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "human" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Sessão de conversa (a mesma do thread do agente: dono::sessão). Nula nas
    # mensagens antigas, gravadas antes de o histórico ser por sessão.
    session_id = Column(String(100), nullable=True, index=True)
