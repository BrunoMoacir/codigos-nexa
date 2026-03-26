# app/models/architect.py
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class ArchitectSimulation(Base):
    __tablename__ = "architect_simulations"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Parâmetros de entrada
    target_amount = Column(Float, nullable=False)
    asset_type = Column(String(20), nullable=False)
    amortization_type = Column(String(10), nullable=True)
    financing_months = Column(Integer, nullable=True)
    down_payment = Column(Float, nullable=True)
    max_monthly_budget = Column(Float, nullable=True)

    # Resultado
    recommended_strategy = Column(String(20), nullable=False)
    confidence_score = Column(Float, nullable=False)
    liquidity_impact = Column(Float, nullable=True)
    months_to_achieve = Column(Integer, nullable=True)
    expected_cost = Column(Float, nullable=True)

    # Payload completo (JSON)
    request_json = Column(Text, nullable=False)
    response_json = Column(Text, nullable=False)

    __table_args__ = (
        Index("idx_arch_sim_user_date", "user_id", created_at.desc()),
        Index("idx_arch_sim_user_asset", "user_id", "asset_type"),
    )


class ArchitectSimulationMetrics(Base):
    __tablename__ = "architect_simulation_metrics"

    user_id = Column(String(100), primary_key=True)
    total_simulations = Column(Integer, nullable=False, default=0)
    last_simulated_at = Column(DateTime(timezone=True), nullable=True)
    favorite_strategy = Column(String(20), nullable=True)
    avg_confidence_score = Column(Float, nullable=True)
    first_simulated_at = Column(DateTime(timezone=True), nullable=True)
