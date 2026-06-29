"""
app/viral/models.py — V1/V2: Viral & Wrapped

Modelos Pydantic para o cartão de economia compartilhável (V1)
e o relatório anual "Banco vs Você" (V2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SavingsSource(BaseModel):
    name: str           # "Otimizador de Cartões", "Raio-X de Tarifas", etc.
    module: str         # "optimizer", "costs", "negotiator", "opportunities"
    annual_savings_brl: float
    description: str    # frase curta legível pelo usuário


class SavingsCard(BaseModel):
    user_id: str
    generated_at: datetime
    total_annual_savings_brl: float
    sources: list[SavingsSource]
    months_active: int
    tagline: str        # "A Nexa te ajudou a guardar R$X"


class WrappedHighlight(BaseModel):
    category: str       # "biggest_waste", "worst_fee", "best_card_missed", "idle_money", "score_evolution"
    title: str
    value_formatted: str    # ex: "R$ 1.234,00" ou "82 pontos"
    description: str


class WrappedReport(BaseModel):
    user_id: str
    year: int
    generated_at: datetime
    highlights: list[WrappedHighlight]
    total_fees_paid_year: float
    total_savings_identified: float
    score_start: Optional[int] = None
    score_end: Optional[int] = None
    score_delta: Optional[int] = None
    badges_earned: list[str] = []
    summary_tagline: str
