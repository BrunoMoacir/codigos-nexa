"""
app/tax/models.py — T1/T2: Otimização de IR em Investimentos

Modelos Pydantic para análise fiscal da carteira de investimentos.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


OpportunityType = Literal[
    "switch_to_lci",
    "switch_to_lca",
    "harvest_loss",
    "avoid_come_cotas",
    "hold_longer",
]


class InvestmentPosition(BaseModel):
    bank_name: str
    product_name: str
    product_type: str          # CDB, LCI, LCA, CRI, CRA, FUNDO_RF, FUNDO_MM, TESOURO, ACAO
    amount: float              # valor investido original (R$)
    current_balance: float     # saldo atual (R$)
    annual_rate_pct: float     # taxa anual (%) — 0 quando desconhecida
    holding_months: int        # meses desde a aplicação
    is_exempt: bool
    unrealized_gain: float     # current_balance − amount (pode ser negativo)
    estimated_ir: float        # IR estimado se resgatar hoje (R$)
    has_come_cotas: bool       # True para fundos RF/multimercado (come-cotas em mai/nov)
    due_date: Optional[date] = None


class TaxOpportunity(BaseModel):
    opportunity_type: OpportunityType
    title: str
    description: str
    position_ref: str          # identificador legível: "Banco X — CDB 12,5%"
    recommended_action: str
    estimated_tax_saving_brl: float
    confidence: Literal["high", "medium", "low"]
    action_deadline: Optional[str] = None   # ex: "antes de 31/05 (come-cotas)"


class TaxAnalysisResponse(BaseModel):
    user_id: str
    generated_at: datetime
    portfolio: list[InvestmentPosition]
    total_invested: float
    total_current_balance: float
    total_unrealized_gain: float
    total_estimated_ir_liability: float    # IR total se resgatar tudo hoje
    opportunities: list[TaxOpportunity]
    total_estimated_tax_saving: float
    summary: str
    data_source: Literal["pluggy", "no_data"]


class BreakevenRequest(BaseModel):
    cdb_rate_pct: float
    holding_months: int = 12
    lci_offered_rate_pct: Optional[float] = None


class BreakevenResponse(BaseModel):
    cdb_rate_pct: float
    holding_months: int
    ir_rate_pct: float
    cdb_net_rate_pct: float
    lci_breakeven_pct: float
    lci_advantage_pct: Optional[float] = None
    interpretation: str
