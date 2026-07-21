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

# Gap 5 (docs/OPP.md §14) — disclaimer regulatório obrigatório em toda
# resposta que compara/recomenda produtos de investimento. Texto único para
# API, chat e feed; revisar com jurídico antes de alterar.
DISCLAIMER = (
    "A Nexa não presta consultoria de valores mobiliários regulada pela CVM. "
    "As comparações usam taxas públicas e regras fiscais vigentes; rentabilidades "
    "passadas não garantem resultados futuros. A decisão de investir é sua — "
    "avalie sua liquidez e seus objetivos antes de aplicar."
)

# Transparência de origem de dados (docs/OPP.md §9.2)
DATA_SOURCES = [
    "CDI: ANBIMA / BCB SGS",
    "SELIC e TR: Banco Central do Brasil (SGS)",
    "Catálogo de produtos: Open Finance Dados Abertos + curadoria Nexa",
    "IR: tabela regressiva (Lei 8.981/1995, art. 65)",
]


class OpportunityItem(BaseModel):
    rank: int
    bank_name: str
    product_type: str           # "CDB" | "LCI" | "LCA" | "TESOURO_SELIC"
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
    # ── V2 (docs/OPP.md §9.1) ──
    index: str = "CDI"          # "CDI" | "SELIC" — indexador do produto
    fgc_covered: bool = True    # garantia FGC até R$250k (False para Tesouro: garantia soberana)
    steps: list[str] = []       # OPP.5 — passos práticos para executar a troca
    # V3 (F8) — taxa acima de 130% do CDI marcada pelo conector como teaser
    # promocional (prazo curto/teto baixo/só clientes novos): rebaixada no
    # ranking em relação a taxas permanentes, mas mantida visível
    promotional: bool = False
    cdi_pct_max: float | None = None  # "até X% do CDI" quando o emissor publica faixa máxima


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

    # V2 (docs/OPP.md §9.2 / Gap 5) — disclaimer regulatório e transparência
    disclaimer: str = ""
    data_sources: list[str] = []

    # Opção B do plano OPP.1 — origem do saldo bruto usado na detecção:
    # "REAL_BALANCE" = saldo real de conta corrente (account_balances/Pluggy);
    # "CASHFLOW_PROXY" = soma cumulativa de transações (aproximação).
    idle_source: Literal["REAL_BALANCE", "CASHFLOW_PROXY"] = "CASHFLOW_PROXY"
    balance_captured_at: Optional[datetime] = None


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


class SavingsVsCdiResult(BaseModel):
    """Ticket OPP4-C — comparação genérica poupança vs. CDI.

    Não depende de saldo real do usuário (Opção A do plano OPP.4) — a mesma
    resposta vale para qualquer usuário num dado dia, calculada para um valor
    de referência (`amount_reference_brl`, default 10_000).

    `cdi_reference_annual_pct`: decisão registrada (não deixar em aberto) —
    usa CDI BRUTO como referência, igual a `cdi_annual_pct`. Poupança é isenta
    de IR e CDI/CDB não; comparar bruto contra bruto é a leitura mais simples
    e defensável sem simular alíquota de IR (que dependeria de holding_months,
    fora do escopo de uma comparação "hoje, sem contexto de prazo"). Campo
    mantido separado de `cdi_annual_pct` para permitir trocar a metodologia de
    referência (ex: CDI líquido simulado) no futuro sem quebrar o contrato.
    """
    amount_reference_brl: float
    savings_annual_pct: float
    cdi_annual_pct: float
    cdi_reference_annual_pct: float
    spread_pct_points: float
    estimated_loss_monthly_brl: float
    estimated_loss_annual_brl: float
    status: Literal["BELOW_CDI", "NEAR_CDI", "NO_ADVANTAGE", "DATA_UNAVAILABLE"]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str
    generated_at: datetime

    # ── OPP4-E — personalização com saldo real de poupança (Pluggy) ──
    # Quando is_personalized=True, amount_reference_brl É o saldo real do
    # usuário (account_balances) e o texto pode afirmar "você tem R$ X".
    # Quando False, é o valor de referência genérico (nunca afirmar saldo).
    is_personalized: bool = False
    savings_balance_brl: Optional[float] = None
    balance_captured_at: Optional[datetime] = None


class CompareRequest(BaseModel):
    amount: float
    holding_months: int = 12


class CompareResponse(BaseModel):
    amount: float
    holding_months: int
    cdi_annual_pct: float
    opportunities: list[OpportunityItem]
    disclaimer: str = ""


# ── OPP.3 — Tesouro SELIC vs. CDB vs. Poupança ────────────────────────

class TreasuryComparisonEntry(BaseModel):
    """Uma das três pernas da comparação OPP.3, em rendimento líquido."""
    label: str                       # "Tesouro SELIC" | "CDB {banco} {pct}% CDI" | "Poupança"
    investment_type: str             # "TESOURO_SELIC" | "CDB" | "POUPANCA"
    annual_rate_gross_pct: float
    annual_rate_net_pct: float       # após IR e custos (custódia B3 no Tesouro)
    net_yield_brl: float             # rendimento líquido no período (R$)
    ir_rate: float
    is_exempt: bool
    fees_brl: float = 0.0            # custódia B3 (só Tesouro)
    fgc_covered: bool
    liquidity: str


class TreasuryComparisonResponse(BaseModel):
    """OPP.3 — comparação a três: Tesouro SELIC vs. melhor CDB vs. poupança.

    Não depende de dados do usuário — é uma simulação para amount/prazo
    informados, com taxas reais (SELIC/TR via BACEN, CDI via ANBIMA).
    """
    amount: float
    holding_months: int
    selic_annual_pct: float
    cdi_annual_pct: float
    savings_annual_pct: float
    entries: list[TreasuryComparisonEntry]   # ordenadas por net_yield_brl desc
    winner: str                              # label da melhor opção
    winner_vs_savings_brl: float             # quanto a melhor opção rende a mais que a poupança
    recommendation: str
    disclaimer: str = ""
    generated_at: datetime


# ── V2 — Scorecard por banco (docs/OPP.md §8.2) ───────────────────────

class BankScorecardEntry(BaseModel):
    bank_name: str
    best_product_type: str
    best_cdi_pct: float
    best_net_annual_rate_pct: float
    best_net_return_brl: float
    best_risk_adjusted_brl: float
    risk_tier: int                  # 1=bancão, 2=digital consolidado, 3=médio/pequeno
    product_count: int
    fgc_covered: bool
    is_user_current_bank: bool      # cruza com pluggy_items.connector_name


class BankComparisonResponse(BaseModel):
    user_id: str
    amount: float
    holding_months: int
    cdi_annual_pct: float
    scorecard: list[BankScorecardEntry]      # ranking por best_risk_adjusted_brl desc
    best_by_liquidity: dict[str, str]        # bucket → bank_name
    user_current_bank: Optional[str] = None
    user_current_bank_rank: Optional[int] = None
    switch_gain_brl: float = 0.0             # melhor banco − banco atual (R$/ano líquido)
    open_account_suggestion: Optional[str] = None
    disclaimer: str = ""
    generated_at: datetime


# ── Bank Match — melhor banco para o usuário (camada de inteligência) ─

class BankMatchComponents(BaseModel):
    """Notas 0–100 de cada pilar do match, antes da ponderação."""
    yield_score: float          # rendimento líquido ajustado a risco (scorecard)
    fees_score: float           # custo projetado de tarifas no banco
    card_score: float           # força dos cartões do banco para o perfil de gasto
    fit_score: float            # aderência ao perfil (risco, liquidez, FGC, amplitude)


class BankMatchEntry(BaseModel):
    bank_name: str
    match_score: float                  # 0–100, ponderado pelo perfil do usuário
    components: BankMatchComponents
    reasons: list[str]                  # explicações humanas (transparência do score)
    risk_tier: int
    is_user_current_bank: bool
    projected_annual_gain_brl: float    # melhor produto do banco p/ o valor simulado
    projected_monthly_fee_brl: float    # tarifa média de mercado do banco
    top_card_name: Optional[str] = None # melhor cartão do banco p/ o perfil (se houver)


class BankMatchResponse(BaseModel):
    """Resposta do GET /opportunities/{user_id}/bank-match.

    Camada de inteligência acima do scorecard: em vez de responder só
    "qual banco paga mais pelo investimento?", responde "qual é o melhor
    banco PARA VOCÊ?", ponderando rendimento, tarifas, cartões e o perfil
    financeiro (FSS, tipo de investidor) do usuário.
    """
    user_id: str
    amount_simulated: float
    holding_months: int
    profile_used: dict                   # fss_level, investor_type, pesos aplicados
    ranking: list[BankMatchEntry]        # ordenado por match_score desc
    user_current_bank: Optional[str] = None
    user_current_bank_rank: Optional[int] = None
    best_bank: Optional[str] = None
    switch_recommendation: str
    disclaimer: str = ""
    data_sources: list[str] = []
    generated_at: datetime


# ── V2 — Catálogo público (transparência) ─────────────────────────────

class CatalogProduct(BaseModel):
    """Produto do catálogo, no schema do bank_products.json + campos V2."""
    bank_name: str
    product_type: str
    cdi_pct: float
    min_amount: float
    liquidity: str
    liquidity_days: int
    rating: str = "N/A"
    index: str = "CDI"
    is_tax_exempt: bool = False
    fgc_covered: bool = True


class ProductCatalogResponse(BaseModel):
    updated_at: str
    source: str                     # "curated" | "open_finance"
    institution_count: int
    product_count: int
    products: list[CatalogProduct]
