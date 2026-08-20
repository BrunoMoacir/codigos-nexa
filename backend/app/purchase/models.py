"""
app/purchase/models.py — Schemas do F7: Modo Compra Inteligente

Tipos de entrada e saída do PurchaseAdvisor.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# Reutiliza o mesmo tipo já definido no projeto
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class PaymentMethod(str, Enum):
    PIX_AVISTA        = "PIX_AVISTA"
    CARTAO_AVISTA     = "CARTAO_AVISTA"
    CARTAO_PARCELADO  = "CARTAO_PARCELADO"
    FINANCIAMENTO     = "FINANCIAMENTO"


class PurchaseRequest(BaseModel):
    user_id: str = Field(..., description="ID do usuário")
    amount: float = Field(..., gt=0, description="Valor da compra (R$)")
    category: str = Field(..., description="Categoria da compra (ex: Eletrônicos, Viagem)")
    installments: int = Field(default=1, ge=1, le=48, description="Parcelas desejadas (1 = à vista)")
    monthly_income: Optional[float] = Field(default=None, gt=0, description="Renda mensal (R$) para elegibilidade de cartões")
    risk_profile: Optional[Literal["conservador", "moderado", "agressivo"]] = Field(
        default=None,
        description="Perfil de risco do usuário (consistente com Architect F3)",
    )
    cash_price: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Preço à vista (PIX/dinheiro) quando a loja dá desconto. "
            "Ausente = mesmo valor de `amount`."
        ),
    )
    installments_total: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Total do parcelado quando é MAIOR que `amount` — o 'sem juros' "
            "que embute juros no preço. Ausente = igual a `amount`."
        ),
    )
    apply_opportunity_cost: bool = Field(
        default=True,
        description="Aplicar custo de oportunidade de capital (CDI) no ranking de opções",
    )

    @model_validator(mode="after")
    def _precos_coerentes(self) -> "PurchaseRequest":
        """
        O desconto à vista é a pergunta de abertura da feature — "Pix com 10%
        ou 12x sem juros?" — e não havia onde informá-lo: com um preço só, o
        PIX perde por construção, porque carrega custo de oportunidade e nenhum
        ganho. Praticado no varejo brasileiro e legal desde 2022.
        """
        if self.cash_price is not None and self.cash_price > self.amount:
            raise ValueError(
                "cash_price não pode ser maior que amount — se o à vista é mais "
                "caro, informe o valor cheio em amount."
            )
        if self.installments_total is not None and self.installments_total < self.amount:
            raise ValueError(
                "installments_total não pode ser menor que amount — se o "
                "parcelado é mais barato, ele é o preço de referência."
            )
        return self

    @field_validator("category")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        return v.strip().capitalize()

    model_config = {"json_schema_extra": {
        "example": {
            "user_id": "user_123",
            "amount": 3000.0,
            "cash_price": 2700.0,
            "category": "Eletrônicos",
            "installments": 12,
        }
    }}


class PaymentOption(BaseModel):
    method: PaymentMethod
    label: str                              # "PIX à vista", "Cartão Nubank (12x)", etc.
    total_cost: float                       # custo total efetivo (R$)
    monthly_cost: Optional[float] = None   # parcela mensal se parcelado/financiado
    installments: Optional[int] = None
    reward_value: float = 0.0              # retorno estimado em cashback/pontos (R$)
    net_cost: Optional[float] = Field(
        default=None,
        description="Custo líquido = total_cost - reward_value. Calculado automaticamente se não informado.",
    )
    notes: str = ""                        # taxa de juros, cartão recomendado, etc.
    opportunity_cost_gain: float = 0.0     # ganho CDI ao não desembolsar à vista (R$)
    net_cost_real: Optional[float] = None  # net_cost - opportunity_cost_gain
    profile_fit: Literal["IDEAL", "OK", "CAUTELA", "EVITAR"] = "OK"

    @model_validator(mode="after")
    def fill_net_cost(self) -> "PaymentOption":
        if self.net_cost is None:
            self.net_cost = round(self.total_cost - self.reward_value, 2)
        if self.net_cost_real is None:
            self.net_cost_real = round(self.net_cost - self.opportunity_cost_gain, 2)
        return self


class LiquidityImpact(BaseModel):
    safe_to_spend_before: float
    safe_to_spend_after: float
    affordable: bool                        # True se net_cost <= safe_to_spend_before
    risk_level: RiskLevel


class PurchaseRecommendation(BaseModel):
    user_id: str
    amount: float
    category: str
    recommended_method: PaymentMethod
    recommended_label: str
    recommended_net_cost: float             # custo líquido da opção recomendada (total - reward)
    reasoning: str                          # explicação em linguagem natural
    options: list[PaymentOption]            # todas as opções ranqueadas (melhor → pior)
    liquidity_impact: LiquidityImpact
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Score 0–1 baseado na qualidade dos dados: "
            "+0.4 se histórico de transações disponível, "
            "+0.3 se safe_to_spend calculado via F1, "
            "+0.3 se monthly_income informado. "
            "Reduzido por warnings gerados."
        ),
    )
    data_sources: list[str] = []
    warnings: list[str] = []
    invoice_horizon: Optional[dict] = None     # pressão da fatura atual (InvoiceHorizon serializado)
    pressure_score: Optional[float] = None     # 0.0–1.0: pressão financeira do perfil
    profile_summary: Optional[str] = None      # texto curto do perfil detectado
    cdi_rate_used: Optional[float] = None      # taxa CDI anual utilizada no cálculo
