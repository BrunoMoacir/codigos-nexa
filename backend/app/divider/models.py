# app/models/context_override.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class ContextOverride(Base):
    __tablename__ = "context_overrides"

    id = Column(String, primary_key=True, index=True)
    transaction_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    original_context = Column(String)
    corrected_context = Column(String)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
