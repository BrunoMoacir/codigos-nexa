# app/jobs/models_orm.py — série temporal de métricas de inteligência
from sqlalchemy import Column, String, Float, Integer, Date, DateTime
from app.core.database import Base


class IntelligenceMetric(Base):
    """
    Uma linha por dia × métrica × dimensão (job intelligence_metrics, 05h30).

    Exemplos:
      (2026-07-19, reco_acceptance_rate, CARD_SWITCH, 0.42, 57)
      (2026-07-19, negotiation_realization_factor, JUROS_ROTATIVO_ALTO, 0.63, 12)
      (2026-07-19, fee_baseline_coverage, open_finance, 28, 28)

    É a matéria-prima do monitoramento de acurácia em produção: tendência de
    aceitação por tipo de insight, realização real vs. estimado do negociador
    e cobertura dos catálogos vivos.
    """

    __tablename__ = "intelligence_metrics"

    metric_date = Column(Date, primary_key=True)
    metric_key = Column(String(60), primary_key=True)
    dimension = Column(String(60), primary_key=True, default="_")
    value = Column(Float, nullable=False)
    samples = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), nullable=True)
