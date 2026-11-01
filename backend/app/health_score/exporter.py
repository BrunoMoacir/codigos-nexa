"""Exportação segura dos indicadores agregados do HIVE Score."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.health_score.router import HealthScoreHistoryResponse


class HiveScoreExport(BaseModel):
    """Contrato versionado para compartilhamento do score financeiro."""

    schema_version: str = "1"
    generated_at: datetime
    score: int = Field(ge=0, le=100)
    trend: str
    change_30d: int | None = None
    change_90d: int | None = None
    resilience_score: int | None = Field(default=None, ge=0, le=100)
    fss_score: float | None = Field(default=None, ge=0, le=100)
    fss_level: str | None = None
    data_quality: str
    history: list[dict[str, Any]]
    disclaimer: str


def build_hive_score_export(
    history: HealthScoreHistoryResponse,
) -> HiveScoreExport:
    """Converte a resposta interna em um documento sem dados brutos."""
    return HiveScoreExport(
        generated_at=datetime.now(timezone.utc),
        score=history.current_score,
        trend=history.trend,
        change_30d=history.change_30d,
        change_90d=history.change_90d,
        resilience_score=history.resilience_score,
        fss_score=history.fss_score,
        fss_level=history.fss_level,
        data_quality=history.data_quality,
        history=[
            {
                "date": point.date,
                "score": point.score,
                "savings_rate": point.savings_rate,
                "profile_type": point.profile_type,
            }
            for point in history.history
        ],
        disclaimer=(
            "Score educacional baseado nos dados disponíveis na Nexa. "
            "Não constitui classificação de crédito nem recomendação financeira."
        ),
    )


__all__ = ["HiveScoreExport", "build_hive_score_export"]
