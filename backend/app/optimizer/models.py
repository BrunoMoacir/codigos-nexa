# app/optimizer/models.py
# Pydantic schemas para o módulo Nexa Optimizer (Funcionalidade 2)
# Somente estrutura e tipos, sem lógica de negócio.

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class CardType(str, Enum):
    POINTS = "POINTS"
    CASHBACK = "CASHBACK"
    INVESTBACK = "INVESTBACK"


class BenefitTag(str, Enum):
    TRAVEL = "TRAVEL"
    CASHBACK = "CASHBACK"
    LOUNGE = "LOUNGE"
    INSURANCE = "INSURANCE"
    INTERNACIONAL = "INTERNACIONAL"
    PREMIUM = "PREMIUM"


class CardFlag(str, Enum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    ELO = "ELO"
    AMEX = "AMEX"
    HIPERCARD = "HIPERCARD"


class RecommendationType(str, Enum):
    SWITCH_RECOMMENDED = "SWITCH_RECOMMENDED"
    KEEP_CURRENT = "KEEP_CURRENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class LiquidityRisk(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─── Modelos de entrada ────────────────────────────────────────────────────────

class OptimizationRequest(BaseModel):
    """Entrada para o endpoint POST /optimizer/analyze/{user_id}"""
    user_id: str
    current_cards: list[str] = []       # IDs dos cartões que o usuário já possui
    safe_to_spend: Optional[float] = None   # injetado pela rota via F1
    monthly_income: Optional[float] = None  # fallback se safe_to_spend=None

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id é obrigatório")
        return v


# ─── CardRecord (schema interno da base de conhecimento) ─────────────────────

class WaiverRules(BaseModel):
    type: str              # "spend_threshold" | "always_free" | "none" | "transaction_count"
    threshold: Optional[float] = None
    count_monthly: Optional[int] = None
    description: str


class CardRecord(BaseModel):
    """Representa um cartão carregado do knowledge_cards.json"""
    card_id: str
    name: str
    issuer: str
    flag: CardFlag
    card_type: CardType
    public_target: str
    min_income: float           # renda anual mínima em R$
    requires_proof_of_income: bool
    secured_card: bool
    prepaid: bool
    consigned: bool
    base_annuity: float
    waiver_rules: WaiverRules
    cashback_pct: Optional[float] = None
    cashback_cap: Optional[float] = None
    cashback_categories: list[str] = []
    points_per_brl: Optional[float] = None
    points_currency: str = "pontos"
    points_conversion_rate: float = 0.0
    benefit_tags: list[BenefitTag] = []
    benefits_detail: list[str] = []
    revolving_interest_monthly: float = 0.0
    installment_interest_monthly: Optional[float] = None
    data_trust_score: float = 0.7
    request_link: Optional[str] = None
    last_updated: str


# ─── Modelos de saída ─────────────────────────────────────────────────────────

class CardSimulationResult(BaseModel):
    """Resultado da simulação para um único cartão"""
    card_id: str
    card_name: str
    issuer: str
    flag: CardFlag
    annuity_effective: float
    annuity_waived: bool
    points_value_min: float
    points_value_expected: float
    points_value_max: float
    net_gain_min: float
    net_gain_expected: float
    net_gain_max: float
    liquidity_impact: float
    liquidity_risk: LiquidityRisk
    confidence_score: float
    eligibility_score: float
    warnings: list[str] = []
    profile_match_reasons: list[str] = []
    spending_anchor: dict = {}
    explanation_steps: list[str] = []
    benefit_highlights: list[str] = []
    benefit_tags: list[BenefitTag] = []


class OptimizationReport(BaseModel):
    """Saída final do Optimizer — devolvida ao endpoint e salva no DuckDB"""
    report_id: str
    user_id: str
    generated_at: datetime
    recommendation_type: RecommendationType
    best_card: Optional[CardSimulationResult] = None
    all_cards: list[CardSimulationResult] = []
    user_profile_summary: dict = {}
    data_sources: list[str] = []
    strategy_text: str = ""
    warnings: list[str] = []
