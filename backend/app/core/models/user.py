# app/models/user.py
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    email_verified = Column(Boolean, default=False, nullable=False, server_default="false")
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    # Corte de sessão: todo token emitido ANTES deste instante é rejeitado.
    # É o que faltava para "trocar a senha derruba as sessões abertas" — sem
    # isso, um access roubado sobrevivia à troca por até 30 min e um refresh
    # roubado por até 14 DIAS, que é a janela que importa.
    # Nulo = nunca houve corte (contas antigas seguem valendo).
    sessions_valid_from = Column(DateTime(timezone=True), nullable=True)
