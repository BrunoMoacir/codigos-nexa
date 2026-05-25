# app/models/architect.py
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, DateTime, Index
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


class SimulationFeedback(Base):
    """Feedback coletado ~6 meses após uma simulação para calibração contínua."""
    __tablename__ = "architect_simulation_feedback"

    id = Column(String(36), primary_key=True)
    simulation_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    # Resultado observado
    feedback_followed = Column(Boolean, nullable=False)
    strategy_used = Column(String(20), nullable=False)

    # Desvios quantitativos (opcionais — usuário pode não saber)
    npv_deviation = Column(Float, nullable=True)         # (real - proj) / |proj|
    rate_deviation = Column(Float, nullable=True)        # taxa_real - taxa_proj (pp)

    # Campos específicos por estratégia
    actual_contemplation_month = Column(Integer, nullable=True)  # CONSORTIUM
    actual_rate_obtained = Column(Float, nullable=True)          # FINANCING

    # Estado do score no momento da simulação (para isotonic regression)
    risk_score_at_simulation = Column(Float, nullable=True)
    risk_profile_at_simulation = Column(String(20), nullable=True)
    confidence_score_at_simulation = Column(Float, nullable=True)

    # Redundante mas útil para agrupar calibração sem JOIN
    asset_type = Column(String(20), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_arch_fb_sim_user", "simulation_id", "user_id"),
    )


class CalibrationState(Base):
    """
    Estado global de calibração — linha única (id=1).

    Mantém os parâmetros aprendidos dos feedbacks e os valores anteriores
    para rollback. Carregado pelo ArchitectService com TTL de 5 min.
    """
    __tablename__ = "architect_calibration_state"

    id = Column(Integer, primary_key=True, default=1)

    # Limiares de discretização do RiskScorer (substituem as constantes hardcoded)
    threshold_conservative = Column(Float, nullable=False, default=0.35)
    threshold_aggressive = Column(Float, nullable=False, default=0.65)

    # Parâmetros do Monte Carlo de consórcio: JSON {asset_type: {bid_mean_initial, bid_std}}
    bid_params_json = Column(Text, nullable=True)

    # Teto aplicado ao confidence_score em _compute_confidence()
    confidence_threshold_upper = Column(Float, nullable=False, default=1.0)

    # Estado anterior para rollback (previous_* ← current_* antes de cada calibração)
    previous_threshold_conservative = Column(Float, nullable=True)
    previous_threshold_aggressive = Column(Float, nullable=True)
    previous_bid_params_json = Column(Text, nullable=True)
    previous_confidence_threshold_upper = Column(Float, nullable=True)

    # Metadados
    n_feedbacks_used = Column(Integer, nullable=False, default=0)
    last_calibrated_at = Column(DateTime(timezone=True), nullable=True)
    calibration_version = Column(Integer, nullable=False, default=0)
