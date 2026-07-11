"""
app/seasonality/models.py — Schemas Pydantic da Sazonalidade Fiscal (R2.c)
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class SeasonalEventOut(BaseModel):
    """Um evento fiscal ativo, já personalizado para o usuário."""
    event_code: str = Field(..., description="IR_DECLARACAO | IR_RESTITUICAO | IPVA_IPTU | DAS_MEI | DASN_SIMEI | DECIMO_PRIMEIRA | DECIMO_SEGUNDA | FGTS_LUCRO")
    name: str
    description: str
    action_hint: str
    deadline: date
    days_until_deadline: int
    is_obligation: bool = Field(..., description="True = prazo legal com multa; False = direito/planejamento")
    estimated_amount_brl: Optional[float] = Field(
        default=None,
        description="Valor estimado do evento para este usuário (ex: 13º ≈ salário líquido), quando calculável",
    )
    is_personalized: bool = Field(
        default=False,
        description="True quando estimated_amount_brl veio de dados reais do usuário",
    )
    metadata: dict = Field(default_factory=dict)


class SeasonalityResponse(BaseModel):
    user_id: str
    reference_date: date
    total: int
    events: list[SeasonalEventOut]
    profile_signals: dict = Field(
        default_factory=dict,
        description="Sinais usados na personalização (is_mei, has_salary) — transparência do cálculo",
    )


__all__ = ["SeasonalEventOut", "SeasonalityResponse"]
