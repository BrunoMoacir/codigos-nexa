"""
app/opportunities/models.py — Schemas Pydantic para o Radar de Oportunidades (OPP)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel

# Ticket OPP1-C — status de confiança da detecção de dinheiro ocioso.
# Ver docs/OPP1_DINHEIRO_PARADO_PLANO.md seção 5.2 para a tabela de uso por status.
IdleDetectionStatus = Literal["NO_DATA", "PRELIMINARY", "CONFIRMED", "NO_IDLE_MONEY"]


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
    idle_amount: float                # valor final, já líquido de reserva
    gross_idle_amount: float = 0.0    # proxy de saldo, sem proteção de reserva
    emergency_reserve: float = 0.0    # reserva protegida (nunca sugerida para investir)
    reserve_months_applied: int = 0   # 0 quando não foi possível calcular o perfil do usuário
    avg_income_3m: float
    avg_expenses_3m: float
    monthly_loss_in_checking: float  # custo de deixar na conta corrente
    cdi_annual_pct: float
    top_opportunity: Optional[OpportunityItem] = None
    opportunities: list[OpportunityItem]
    recommendation: str
    generated_at: datetime

    # Ticket OPP1-C — threshold de persistência (R$500 / 30 dias)
    is_confirmed_idle: bool = False
    days_tracked: int = 0
    idle_detection_status: IdleDetectionStatus = "NO_DATA"
    idle_detection_reason: str = ""


class SavingsRateResult(BaseModel):
    """Ticket OPP4-B — resultado puro de calculate_savings_rate().

    Regra oficial (Lei 8.177/1991, na redação dada pela Lei 12.703/2012 —
    conhecida à época como MP 567/2012 antes da conversão): recomendado
    confirmar com jurídico/compliance antes de expor como orientação
    financeira ao usuário (ver docs/OPP4_POUPANCA_CDI_PLANO.md, seção 7).
    """
    selic_annual: float
    tr_monthly: float
    savings_monthly: float
    savings_annual: float
    rule_branch: Literal["SELIC_GT_8_5", "SELIC_LTE_8_5"]
    source: Literal["BACEN", "FALLBACK"] = "BACEN"
    generated_at: datetime


class CompareRequest(BaseModel):
    amount: float
    holding_months: int = 12


class CompareResponse(BaseModel):
    amount: float
    holding_months: int
    cdi_annual_pct: float
    opportunities: list[OpportunityItem]
