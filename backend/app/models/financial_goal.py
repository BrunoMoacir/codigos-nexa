# app/models/financial_goal.py
from sqlalchemy import Column, String, Float, Index
from app.core.database import Base


class FinancialGoal(Base):
    __tablename__ = "financial_goals"

    goal_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    goal_type = Column(String, default="outros")
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    target_date = Column(String, nullable=True)
    monthly_contribution_needed = Column(Float, nullable=True)
    monthly_contribution_actual = Column(Float, nullable=True)
    status = Column(String, default="ACTIVE")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_financial_goals_user_status", "user_id", "status"),
    )
