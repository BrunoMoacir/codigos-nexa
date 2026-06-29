"""
app/opportunities/models.py — Schemas Pydantic para o Radar de Oportunidades (OPP)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class OpportunityItem(BaseModel):
    rank: int
    bank_name: str
    product_type: str           # "CDB" | "LCI" | "LCA"
    rating: str                 # "AAA" | "AA" | "A"
    cdi_pct: float              # ex: 110.0 → 110% do CDI
    annual_rate_gross_pct: float
    annual_rate_net_pct: float  # após IR — critério de ranking
    ir_rate: float              # 0.0 para isentos
    is_exempt: bool
    min_amount: float
    liquidity: str              # "daily" | "6m" | "12m" | "24m"
    liquidity_days: int
    monthly_gain_brl: float     # ganho mensal para o idle_amount do usuário
    annual_gain_brl: float
    eligible: bool              # False quando idle_amount < min_amount


class OpportunitiesResponse(BaseModel):
    user_id: str
    idle_amount: float
    avg_income_3m: float
    avg_expenses_3m: float
    monthly_loss_in_checking: float  # custo de deixar na conta corrente
    cdi_annual_pct: float
    top_opportunity: Optional[OpportunityItem] = None
    opportunities: list[OpportunityItem]
    recommendation: str
    generated_at: datetime


class CompareRequest(BaseModel):
    amount: float
    holding_months: int = 12


class CompareResponse(BaseModel):
    amount: float
    holding_months: int
    cdi_annual_pct: float
    opportunities: list[OpportunityItem]
