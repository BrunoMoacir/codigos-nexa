# app/models/transaction.py
from sqlalchemy import Column, Index, String, Float, Date, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class Transaction(Base):
    __tablename__ = "transactions_clean"

    transaction_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    account_id = Column(String, index=True)
    description = Column(String)
    amount = Column(Float)
    date = Column(Date, index=True)

    # Índice composto para queries típicas: WHERE user_id = ? AND date >= ?
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "date"),
    )
    transaction_type = Column(String)
    category = Column(String)
    is_recurring = Column(Boolean, default=False)
    is_installment = Column(Boolean, default=False)
    context_type = Column(String)
    context_confidence = Column(Float)
    context_override_by_user = Column(Boolean, default=False)
    pj_subcategory = Column(String)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
