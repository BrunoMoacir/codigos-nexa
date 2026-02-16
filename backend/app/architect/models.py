"""
app/architect/models.py - Schemas Pydantic da F3 (Nexa Architect)

RESPONSABILIDADE:
    Definir todos os tipos de entrada e saída do simulador de conquistas.
    Compara 3 estratégias: Financiamento | Consórcio | Poupar/Investir.

INTEGRAÇÃO:
    - Consumido por architect_service.py (orquestrador)
    - Consumido por api/v1/routes/architect.py (endpoints REST)
    - Alimentado por daily_forecast e safe_to_spend da F1

USAGE:
    from app.architect.models import (
        SimulationRequest,
        SimulationResponse,
        StrategyType,
        RiskProfile,
    )
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StrategyType(str, Enum):
    """
    Estratégia de aquisição recomendada ou simulada.

    FINANCING    → Comprar agora via crédito bancário (PRICE ou SAC)
    CONSORTIUM   → Entrar em grupo de consórcio (menor custo total)
    SAVE_INVEST  → Poupar e investir até atingir o valor (sem dívida)
    """
    FINANCING   = "FINANCING"
    CONSORTIUM  = "CONSORTIUM"
    SAVE_INVEST = "SAVE_INVEST"


class AmortizationMethod(str, Enum):
    """
    Sistema de amortização para financiamento bancário.

    PRICE → Parcelas fixas (Sistema Francês). Juros pesados no início.
    SAC   → Amortização constante. Parcelas decrescentes, menor custo total.
    """
    PRICE = "PRICE"
    SAC   = "SAC"


class RiskProfile(str, Enum):
    """
    Perfil de risco declarado pelo usuário.

    Influencia a taxa de desconto usada no NPV e a tolerância
    ao impacto de liquidez.

    conservador  → Avesso a dívida, prioriza segurança
    moderado     → Aceita algum risco por melhor custo
    agressivo    → Tolera parcelas altas por aquisição imediata
    """
    CONSERVADOR = "conservador"
    MODERADO    = "moderado"
    AGRESSIVO   = "agressivo"


class AssetType(str, Enum):
    """
    Tipo de bem a ser adquirido.

    Usado para sugerir prazos típicos e taxas de mercado relevantes.

    IMOVEL   → Imóvel residencial ou comercial
    VEICULO  → Automóvel, moto ou caminhão
    REFORMA  → Reforma ou construção
    VIAGEM   → Pacote de viagem
    OUTRO    → Qualquer outro bem de alto valor
    """
    IMOVEL  = "IMOVEL"
    VEICULO = "VEICULO"
    REFORMA = "REFORMA"
    VIAGEM  = "VIAGEM"
    OUTRO   = "OUTRO"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REQUEST — INPUT DO USUÁRIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SimulationRequest(BaseModel):
    """
    Parâmetros de entrada para a simulação de conquistas.

    Campos obrigatórios: user_id e target_amount.
    Todos os demais têm defaults razoáveis para o mercado brasileiro.

    Example:
        >>> req = SimulationRequest(
        ...     user_id="user_123",
        ...     target_amount=100000.0,
        ...     down_payment=10000.0,
        ...     max_monthly_budget=3000.0,
        ...     risk_profile=RiskProfile.MODERADO,
        ... )
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_123",
                "target_amount": 100000.0,
                "target_date": "2028-12-31",
                "down_payment": 10000.0,
                "max_monthly_budget": 3000.0,
                "risk_profile": "moderado",
                "asset_type": "VEICULO",
                "prefers_consortium": False,
                "include_consortium": True,
                "financing_months": 48,
                "amortization_method": "PRICE",
            }
        }
    )

    # ── Obrigatórios ────────────────────────────────────────────────

    user_id: str = Field(
        ...,
        description="ID do usuário (usado para buscar daily_forecast e safe_to_spend da F1)",
        min_length=1,
        max_length=100,
    )

    target_amount: float = Field(
        ...,
        description="Valor total do bem a ser adquirido (R$)",
        gt=0,
        le=50_000_000,
    )

    # ── Opcionais com defaults ───────────────────────────────────────

    target_date: Optional[date] = Field(
        default=None,
        description="Data desejada para aquisição. None = sem prazo definido.",
    )

    down_payment: float = Field(
        default=0.0,
        description="Valor de entrada disponível (R$). Reduz o principal financiado.",
        ge=0,
    )

    max_monthly_budget: Optional[float] = Field(
        default=None,
        description=(
            "Orçamento mensal máximo que o usuário aceita comprometer (R$). "
            "None = usar safe_to_spend da F1."
        ),
        gt=0,
    )

    risk_profile: RiskProfile = Field(
        default=RiskProfile.MODERADO,
        description="Perfil de risco do usuário",
    )

    asset_type: AssetType = Field(
        default=AssetType.OUTRO,
        description="Tipo de bem a ser adquirido",
    )

    prefers_consortium: bool = Field(
        default=False,
        description="Usuário já tem preferência declarada por consórcio",
    )

    include_consortium: bool = Field(
        default=True,
        description="Incluir a estratégia de consórcio na comparação",
    )

    financing_months: int = Field(
        default=48,
        description="Prazo do financiamento em meses",
        ge=6,
        le=420,
    )

    amortization_method: AmortizationMethod = Field(
        default=AmortizationMethod.PRICE,
        description="Sistema de amortização para financiamento",
    )

    # ── Validações de negócio ────────────────────────────────────────

    @field_validator("down_payment")
    @classmethod
    def down_payment_menor_que_target(cls, v: float, info) -> float:
        target = info.data.get("target_amount")
        if target is not None and v >= target:
            raise ValueError(
                f"down_payment ({v}) deve ser menor que target_amount ({target})"
            )
        return v

    @field_validator("target_date")
    @classmethod
    def target_date_no_futuro(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v <= date.today():
            raise ValueError("target_date deve ser uma data futura")
        return v

    @property
    def principal(self) -> float:
        """Valor efetivamente financiado (target - entrada)."""
        return self.target_amount - self.down_payment


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TERMOS DE CADA ESTRATÉGIA (inputs dos calculadores)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FinancingTerms(BaseModel):
    """
    Parâmetros de um financiamento bancário.

    Usados como entrada para calculate_price() / calculate_sac().
    """

    principal: float = Field(
        ...,
        description="Valor financiado (target - entrada), em R$",
        gt=0,
    )
    rate_annual: float = Field(
        ...,
        description="Taxa de juros anual do banco (CET ou nominal), decimal. Ex: 0.12 = 12% a.a.",
        ge=0,
        le=5.0,
    )
    months: int = Field(
        ...,
        description="Prazo do financiamento em meses",
        ge=1,
        le=420,
    )
    method: AmortizationMethod = Field(
        default=AmortizationMethod.PRICE,
        description="Sistema de amortização",
    )
    iof_rate: float = Field(
        default=0.0038,
        description="IOF sobre o principal (default: 0,38%)",
        ge=0,
        le=0.1,
    )
    admin_fee: float = Field(
        default=0.0,
        description="Tarifa administrativa única (R$)",
        ge=0,
    )


class ConsortiumTerms(BaseModel):
    """
    Parâmetros de um consórcio.

    Usados como entrada para o consortium calculator (Fase 2).
    """

    total_value: float = Field(
        ...,
        description="Valor total do bem no consórcio (R$)",
        gt=0,
    )
    months: int = Field(
        ...,
        description="Duração do grupo em meses",
        ge=12,
        le=300,
    )
    admin_rate: float = Field(
        default=0.15,
        description="Taxa de administração total sobre o valor (decimal). Ex: 0.15 = 15%",
        ge=0,
        le=0.3,
    )
    reserve_fund_rate: float = Field(
        default=0.02,
        description="Fundo de reserva total sobre o valor (decimal)",
        ge=0,
        le=0.1,
    )
    lance_percentage: float = Field(
        default=0.0,
        description="Percentual de lance ofertado para antecipar contemplação (0 = sem lance)",
        ge=0,
        le=1.0,
    )


class InvestmentTerms(BaseModel):
    """
    Parâmetros de poupança/investimento para acumular o valor.

    Usados como entrada para investment calculator (future value).
    """

    monthly_deposit: float = Field(
        ...,
        description="Depósito mensal planejado (R$)",
        gt=0,
    )
    rate_annual: float = Field(
        ...,
        description="Taxa de rendimento anual (decimal). Ex: 0.10 = 10% a.a. (CDI)",
        ge=0,
        le=2.0,
    )
    months: int = Field(
        ...,
        description="Prazo de acumulação em meses",
        ge=1,
        le=600,
    )
    initial_amount: float = Field(
        default=0.0,
        description="Valor já poupado / entrada disponível (R$)",
        ge=0,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULTADO DE CADA ESTRATÉGIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CostScenario(BaseModel):
    """
    Cenário de custo total de uma estratégia (pessimista / esperado / otimista).

    Attributes:
        min_cost:      Melhor caso (ex: SAC, lance alto no consórcio, CDI alto)
        expected_cost: Caso base (parâmetros de mercado hoje)
        max_cost:      Pior caso (PRICE, sem lance, CDI baixo)
    """

    min_cost: float = Field(..., description="Custo total mínimo (R$)", ge=0)
    expected_cost: float = Field(..., description="Custo total esperado (R$)", ge=0)
    max_cost: float = Field(..., description="Custo total máximo (R$)", ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "CostScenario":
        if not (self.min_cost <= self.expected_cost <= self.max_cost):
            raise ValueError(
                f"Ordem inválida: min ({self.min_cost}) <= expected ({self.expected_cost}) <= max ({self.max_cost})"
            )
        return self


class NPVComparison(BaseModel):
    """
    Valor Presente Líquido (NPV/VPL) de cada estratégia.

    O NPV representa o custo total trazido a valor presente pela taxa de desconto
    (SELIC). Menor NPV = estratégia mais vantajosa financeiramente.

    Attributes:
        financing:          NPV do financiamento bancário
        consortium:         NPV do consórcio (None se não calculado)
        save_invest:        NPV da estratégia de poupar/investir
        discount_rate_used: Taxa de desconto mensal usada no cálculo
    """

    financing: float = Field(..., description="NPV do financiamento (R$)")
    consortium: Optional[float] = Field(
        default=None,
        description="NPV do consórcio (R$). None se include_consortium=False.",
    )
    save_invest: float = Field(..., description="NPV da estratégia poupar/investir (R$)")
    discount_rate_used: float = Field(
        ...,
        description="Taxa de desconto mensal utilizada (decimal). Ex: 0.00896 = SELIC/12",
        ge=0,
    )


class ConsortiumProbability(BaseModel):
    """
    Probabilidades de contemplação no consórcio ao longo do tempo.

    Calculadas por Monte Carlo (Fase 2). Na Fase 1 são estimativas
    baseadas em estatísticas históricas da ABAC.

    Attributes:
        win_12m:         Probabilidade de ser contemplado em até 12 meses
        win_24m:         Probabilidade de ser contemplado em até 24 meses
        win_36m:         Probabilidade de ser contemplado em até 36 meses
        expected_months: Meses esperados até contemplação
        with_lance:      Se o cálculo considerou oferta de lance
    """

    win_12m: float = Field(..., description="P(contemplado ≤ 12 meses)", ge=0, le=1)
    win_24m: float = Field(..., description="P(contemplado ≤ 24 meses)", ge=0, le=1)
    win_36m: float = Field(..., description="P(contemplado ≤ 36 meses)", ge=0, le=1)
    expected_months: int = Field(
        ..., description="Meses esperados até contemplação", ge=1
    )
    with_lance: bool = Field(
        default=False,
        description="True se os cálculos consideram oferta de lance",
    )

    @model_validator(mode="after")
    def validate_probability_order(self) -> "ConsortiumProbability":
        if not (self.win_12m <= self.win_24m <= self.win_36m):
            raise ValueError(
                "Probabilidades devem ser crescentes: win_12m ≤ win_24m ≤ win_36m"
            )
        return self


class ActionStep(BaseModel):
    """
    Passo individual do plano de ação recomendado.

    Attributes:
        step:        Número sequencial do passo (1, 2, 3...)
        action:      Descrição da ação em linguagem natural
        amount:      Valor envolvido, se aplicável (R$)
        deadline:    Prazo para realizar a ação, se aplicável
        is_critical: Se este passo é bloqueante para os seguintes
    """

    step: int = Field(..., description="Número sequencial", ge=1)
    action: str = Field(..., description="Descrição da ação", min_length=5, max_length=300)
    amount: Optional[float] = Field(
        default=None, description="Valor financeiro do passo (R$)", ge=0
    )
    deadline: Optional[date] = Field(
        default=None, description="Data limite para executar o passo"
    )
    is_critical: bool = Field(
        default=False,
        description="Se verdadeiro, passo não pode ser pulado",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE — OUTPUT DA SIMULAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SimulationResponse(BaseModel):
    """
    Resultado completo da simulação de conquistas.

    Retornado pelo endpoint POST /architect/simulate.
    Contém a estratégia recomendada, comparação de custos e NPV,
    impacto de liquidez, plano de ação e score de confiança.

    Example:
        >>> response = SimulationResponse(
        ...     recommended_strategy=StrategyType.CONSORTIUM,
        ...     costs=CostScenario(min_cost=98000, expected_cost=103400, max_cost=111000),
        ...     npv=NPVComparison(financing=105000, consortium=103400, save_invest=120000,
        ...                       discount_rate_used=0.00896),
        ...     liquidity_impact=-0.22,
        ...     months_to_achieve=36,
        ...     action_plan=[ActionStep(step=1, action="Dar entrada de R$ 10.000", amount=10000)],
        ...     confidence_score=0.71,
        ...     data_sources=["shadow_invoice", "daily_forecast", "bacen"],
        ... )
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "recommended_strategy": "CONSORTIUM",
                "costs": {
                    "min_cost": 98000,
                    "expected_cost": 103400,
                    "max_cost": 111000,
                },
                "npv": {
                    "financing": 105000,
                    "consortium": 103400,
                    "save_invest": 120000,
                    "discount_rate_used": 0.00896,
                },
                "consortium_probability": {
                    "win_12m": 0.46,
                    "win_24m": 0.78,
                    "win_36m": 0.93,
                    "expected_months": 26,
                    "with_lance": False,
                },
                "liquidity_impact": -0.22,
                "months_to_achieve": 36,
                "action_plan": [
                    {
                        "step": 1,
                        "action": "Dar entrada de R$ 10.000",
                        "amount": 10000,
                        "deadline": None,
                        "is_critical": True,
                    }
                ],
                "confidence_score": 0.71,
                "data_sources": ["shadow_invoice", "daily_forecast", "bacen", "anbima"],
                "generated_at": "2026-02-16T10:00:00",
                "warnings": [],
            }
        }
    )

    # ── Resultado central ────────────────────────────────────────────

    recommended_strategy: StrategyType = Field(
        ...,
        description="Estratégia com menor NPV considerando o perfil do usuário",
    )

    costs: CostScenario = Field(
        ...,
        description="Custo total (mín/esperado/máx) da estratégia recomendada",
    )

    npv: NPVComparison = Field(
        ...,
        description="NPV de cada estratégia para comparação direta",
    )

    # ── Consórcio (opcional — presente quando include_consortium=True) ──

    consortium_probability: Optional[ConsortiumProbability] = Field(
        default=None,
        description="Probabilidades de contemplação (presente quando consórcio foi simulado)",
    )

    # ── Liquidez e prazo ────────────────────────────────────────────

    liquidity_impact: float = Field(
        ...,
        description=(
            "Impacto sobre a liquidez mensal do usuário: "
            "parcela / safe_to_spend. Negativo = consumo do orçamento. "
            "Ex: -0.22 = estratégia consome 22% do safe-to-spend."
        ),
    )

    months_to_achieve: int = Field(
        ...,
        description="Meses até aquisição ou quitação total do bem",
        ge=1,
    )

    # ── Plano de ação ───────────────────────────────────────────────

    action_plan: list[ActionStep] = Field(
        ...,
        description="Passos práticos recomendados em ordem sequencial",
        min_length=1,
        max_length=10,
    )

    # ── Qualidade e rastreabilidade ─────────────────────────────────

    confidence_score: float = Field(
        ...,
        description=(
            "Score de confiança da recomendação (0.0–1.0). "
            "Penalizado quando dados da F1 estão ausentes ou desatualizados."
        ),
        ge=0.0,
        le=1.0,
    )

    data_sources: list[str] = Field(
        ...,
        description="Fontes de dados usadas na simulação",
    )

    generated_at: datetime = Field(
        default_factory=datetime.now,
        description="Data/hora de geração da simulação",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Alertas não-bloqueantes: liquidez apertada, dados desatualizados, "
            "parcela acima do orçamento, etc."
        ),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REPORT — PERSISTÊNCIA NO BANCO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SimulationReport(BaseModel):
    """
    Registro de simulação para persistência no banco de dados.

    Combina o request original com o response gerado e metadados
    de auditoria. Mapeado para a tabela architect_simulations.

    Attributes:
        simulation_id: UUID gerado pelo banco
        user_id:       ID do usuário
        request:       Parâmetros de entrada originais
        response:      Resultado completo da simulação
        created_at:    Timestamp de criação
        duration_ms:   Tempo de processamento em milissegundos
    """

    simulation_id: str = Field(
        ...,
        description="UUID único da simulação (gerado pelo banco)",
        min_length=36,
        max_length=36,
    )

    user_id: str = Field(
        ...,
        description="ID do usuário dono da simulação",
        min_length=1,
        max_length=100,
    )

    request: SimulationRequest = Field(
        ..., description="Parâmetros de entrada originais"
    )

    response: SimulationResponse = Field(
        ..., description="Resultado completo da simulação"
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp de persistência",
    )

    duration_ms: Optional[int] = Field(
        default=None,
        description="Tempo de processamento em milissegundos",
        ge=0,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # Enums
    "StrategyType",
    "AmortizationMethod",
    "RiskProfile",
    "AssetType",
    # Request
    "SimulationRequest",
    # Termos das estratégias
    "FinancingTerms",
    "ConsortiumTerms",
    "InvestmentTerms",
    # Componentes do response
    "CostScenario",
    "NPVComparison",
    "ConsortiumProbability",
    "ActionStep",
    # Response
    "SimulationResponse",
    # Persistência
    "SimulationReport",
]
