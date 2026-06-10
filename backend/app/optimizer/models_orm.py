# app/models/optimization_report.py
from sqlalchemy import Column, DateTime, String, Float, Text, text
from app.core.database import Base


class OptimizationReport(Base):
    __tablename__ = "optimization_reports"

    report_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    generated_at = Column(String, nullable=False)
    recommendation_type = Column(String, nullable=False)
    best_card_id = Column(String, nullable=True)
    best_card_name = Column(String, nullable=True)
    net_gain_expected = Column(Float, nullable=True)
    net_gain_min = Column(Float, nullable=True)
    net_gain_max = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    liquidity_impact = Column(Float, nullable=True)
    liquidity_risk = Column(String, nullable=True)
    data_sources = Column(String, nullable=True)
    strategy_text = Column(String, nullable=True)
    warnings = Column(String, nullable=True)
    full_report_json = Column(Text, nullable=True)


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id = Column(String(36), primary_key=True)
    recommendation_id = Column(String(36), nullable=False, index=True)
    insight_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    insight_type = Column(String(50), nullable=False, index=True)
    detector = Column(String(100), nullable=False)
    signals_json = Column(Text, nullable=True)
    outcome = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
