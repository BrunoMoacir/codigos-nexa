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

class CashbackCategoryRule(BaseModel):
    """M2.5 — Regra de cashback diferenciado por categoria."""
    category: str              # ex: "alimentacao", "farmacia", "transporte"
    pct: float                 # percentual de cashback (0.02 = 2%)
    cap_monthly: Optional[float] = None  # teto mensal em R$ (None = sem teto)



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
    cashback_pct: Optional[float] = None    # cashback flat (fallback quando sem categoria)
    cashback_cap: Optional[float] = None    # teto mensal geral do cashback flat
    cashback_default_pct: Optional[float] = None   # M2.5: taxa padrão para categorias sem regra específica
    cashback_categories: list[CashbackCategoryRule] = []  # M2.5: regras por categoria
    points_per_brl: Optional[float] = None
    points_currency: str = "pontos"
    points_conversion_rate: float = 0.0
    # M2.3: programa de fidelidade para valoração dinâmica (livelo, nu_pontos, atomos, smiles, pontos_itau)
    loyalty_program: Optional[str] = None
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
    eligibility_reasons: list[str] = []
    warnings: list[str] = []
    profile_match_reasons: list[str] = []
    spending_anchor: dict = {}
    explanation_steps: list[str] = []
    benefit_highlights: list[str] = []
    benefit_tags: list[BenefitTag] = []
    waiver_threshold: Optional[float] = None  # gasto anual necessário para isentar anuidade


class OptimizationReport(BaseModel):
    """Saída final do Optimizer — devolvida ao endpoint e salva no DuckDB"""
    report_id: str
    user_id: str
    generated_at: datetime
    recommendation_type: RecommendationType
    best_card: Optional[CardSimulationResult] = None
    all_cards: list[CardSimulationResult] = []
    insights: list["ActionableInsight"] = []
    user_profile_summary: dict = {}
    data_sources: list[str] = []
    strategy_text: str = ""
    warnings: list[str] = []
    life_events: list[dict] = []


# ─── Camada 5 — Insights Acionáveis ──────────────────────────────────────────

class InsightType(str, Enum):
    """Taxonomia de insights (seção 7.1 da arquitetura v2.1)."""
    TROCAR_PRIMARIO   = "TROCAR_PRIMARIO"    # Melhor cartão ≠ atual, ganho > R$20/mês
    PORTFOLIO_MULTI   = "PORTFOLIO_MULTI"    # 2+ cartões melhoram retorno > R$30/mês
    ATIVAR_BENEFICIO  = "ATIVAR_BENEFICIO"   # Benefício com utilização < 0.3 e valor > R$20/mês
    CANCELAR_CARTAO   = "CANCELAR_CARTAO"    # Cartão com retorno líquido < -R$15/mês
    ATINGIR_ISENCAO   = "ATINGIR_ISENCAO"    # Gap < 3 meses de gasto para waiver
    MUDAR_CATEGORIA   = "MUDAR_CATEGORIA"    # Cartão existente melhor em categoria não usada
    SOLICITAR_UPGRADE = "SOLICITAR_UPGRADE"  # Usuário atingiu 90%+ dos critérios do próximo tier


class InsightEffort(str, Enum):
    """Esforço necessário para executar o insight."""
    BAIXO = "Baixo"
    MEDIO = "Médio"
    ALTO  = "Alto"


class InsightInterval(BaseModel):
    """
    Intervalo de ganho estimado por percentil (seção 7.2 da arquitetura v2.1).

    conservative (P25): cenário pessimista — usado para MinGainFilter (R$10/mês gate).
    expected     (P50): cenário mais provável — mostrado em destaque ao usuário.
    optimistic   (P75): cenário otimista — mostrado como teto.

    Regra de display:
        optimistic / conservative < 1.5 → mostrar só expected ("R$61/mês")
        optimistic / conservative ≥ 1.5 → mostrar banda ("R$40–R$95/mês") + explicação
    """
    conservative: float   # P25
    expected: float        # P50
    optimistic: float      # P75

    @property
    def show_band(self) -> bool:
        """True quando a incerteza é alta o suficiente para mostrar banda."""
        if self.conservative <= 0:
            return False
        return (self.optimistic / self.conservative) >= 1.5

    def display_text(self) -> str:
        """Texto pronto para exibição ao usuário."""
        if self.show_band:
            return f"R${self.conservative:.0f}–R${self.optimistic:.0f}/mês"
        return f"R${self.expected:.0f}/mês"


class ActionableInsight(BaseModel):
    """
    Insight acionável gerado pela Camada 5 (seção 7 da arquitetura v2.1).

    Ranqueados por priority_score = monthly_gain × effort_multiplier × confidence_score.
    Só são surfaçados se confidence ≥ 0.65 e gain_interval.conservative ≥ R$10/mês.
    """
    type: InsightType
    title: str
    description: str
    gain_interval: InsightInterval
    effort: InsightEffort
    confidence_score: float
    priority_score: float
    card_id: Optional[str] = None
    card_name: Optional[str] = None
    tags: list[str] = []


# ─── M2.4: ROI do Cartão Atual ────────────────────────────────────────────────

class CardROIVerdict(str, Enum):
    VALE_A_PENA = "VALE_A_PENA"        # net_roi positivo — anuidade se paga
    MARGINAL = "MARGINAL"              # net_roi entre -R$200 e R$0 — depende de outros benefícios
    NAO_VALE = "NAO_VALE"              # net_roi abaixo de -R$200 — troca recomendada


class CurrentCardROI(BaseModel):
    """M2.4 — Rastreamento de ROI do cartão atual do usuário."""
    card_id: str
    card_name: str
    annuity_paid: float                      # anuidade anual que está pagando (R$/ano)
    reward_value_generated: float            # valor de pontos/cashback gerado com gasto atual (R$/ano)
    net_roi: float                           # reward - annuity (negativo = prejuízo)
    annuity_waived: bool                     # anuidade está isenta pelo volume de gasto?
    spend_needed_for_waiver: Optional[float] = None  # gasto mensal adicional necessário para isentar (assume 12 meses uniformes; None se já isento ou sem threshold)
    months_to_reach_waiver: Optional[float] = None   # meses no ritmo atual p/ alcançar threshold
    benefits_used: list[str] = []            # benefícios que o perfil indica uso
    benefits_unused: list[str] = []          # benefícios que o perfil NÃO usa
    verdict: CardROIVerdict
    explanation: str
