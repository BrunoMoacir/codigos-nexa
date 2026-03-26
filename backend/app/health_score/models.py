# app/models/health_score.py
from sqlalchemy import Column, String, Integer, Float, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class HealthScoreHistory(Base):
    __tablename__ = "health_score_history"

    user_id = Column(String, primary_key=True)
    date = Column(String, primary_key=True) # YYYY-MM
    health_score = Column(Integer, nullable=False)
    savings_rate = Column(Float)
    profile_type = Column(String)
    safe_to_spend = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
