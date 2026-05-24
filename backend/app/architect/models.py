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
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StrategyType(str, Enum):
    """
    Estratégia de aquisição recomendada ou simulada.

    FINANCING               → Comprar agora via crédito bancário (PRICE ou SAC)
    CONSORTIUM              → Entrar em grupo de consórcio (menor custo total)
    SAVE_INVEST             → Poupar e investir até atingir o valor (sem dívida)
    FINANCING_RENTAL        → Financiamento + aluguel do imóvel (parcela líquida = parcela - aluguel)
    CONSORTIUM_SELIC_RENTAL → Consórcio + entrada investida na SELIC + aluguel cobrindo parcelas
    """
    FINANCING               = "FINANCING"
    CONSORTIUM              = "CONSORTIUM"
    SAVE_INVEST             = "SAVE_INVEST"
    FINANCING_RENTAL        = "FINANCING_RENTAL"
    CONSORTIUM_SELIC_RENTAL = "CONSORTIUM_SELIC_RENTAL"


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
# OPEN FINANCE — FEATURES EXTRAÍDAS DOS ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OpenFinanceFeatures(BaseModel):
    """
    Features personalizadas extraídas dos endpoints do Open Finance Brasil.

    Todos os campos são Optional — a simulação degrada graciosamente quando
    um endpoint não retorna dados ou a permissão não foi concedida.

    Impacto direto no motor:
        rendimento_real_atual    → substitui CDI teórico como taxa de desconto NPV
                                   e benchmark do SAVE_INVEST (elimina a maior suposição)
        cet_historico_real       → substitui CET genérico de mercado pelo CET real
                                   que o banco cobra neste usuário específico
        comprometimento_renda_pct → limita margem disponível; gera aviso de risco
        adimplencia_pct          → desconto no CET estimado (bom pagador = taxa menor)
        meses_consecutivos_poupanca → valida capacidade de poupança declarada
        sazonalidade_receita     → detecta meses de baixa renda onde a parcela pesa

    Fonte por endpoint:
        /investments → rendimento_real_atual, composicao_rf_pct, composicao_rv_pct,
                       duration_media_anos
        /loans       → cet_medio_historico, adimplencia_pct, comprometimento_renda_pct
        /accounts    → sazonalidade_receita, meses_consecutivos_poupanca
        /financings  → experiencia_financiamento, cet_historico_real
    """

    # ── /investments ──────────────────────────────────────────────────

    rendimento_real_atual: Optional[float] = Field(
        default=None,
        description=(
            "Taxa de retorno anual real (líquida de IR) dos investimentos do usuário (decimal). "
            "Ex: 0.12 = 12% a.a. Substitui CDI teórico como benchmark do SAVE_INVEST "
            "e como taxa de desconto do NPV — elimina a principal suposição do modelo."
        ),
        ge=0.0,
        le=1.0,
    )
    composicao_rf_pct: Optional[float] = Field(
        default=None,
        description="Percentual da carteira em renda fixa [0-1].",
        ge=0.0, le=1.0,
    )
    composicao_rv_pct: Optional[float] = Field(
        default=None,
        description="Percentual da carteira em renda variável [0-1].",
        ge=0.0, le=1.0,
    )
    duration_media_anos: Optional[float] = Field(
        default=None,
        description="Duration média ponderada da carteira de renda fixa (anos). "
                    "Alta duration → maior sensibilidade a variações de Selic.",
        ge=0.0,
    )

    # ── /loans ────────────────────────────────────────────────────────

    cet_medio_historico: Optional[float] = Field(
        default=None,
        description=(
            "CET médio anual ponderado pago historicamente em contratos de crédito (decimal). "
            "Inclui crédito pessoal, consignado, etc. Proxy do relacionamento bancário."
        ),
        ge=0.0, le=2.0,
    )
    adimplencia_pct: Optional[float] = Field(
        default=None,
        description=(
            "Percentual de parcelas pagas em dia sobre o total de parcelas [0-1]. "
            "1.0 = adimplência perfeita → CET menor estimado. "
            "< 0.90 → aviso de risco de não-aprovação."
        ),
        ge=0.0, le=1.0,
    )
    comprometimento_renda_pct: Optional[float] = Field(
        default=None,
        description=(
            "Percentual da renda mensal já comprometida com parcelas de dívidas ativas [0-1]. "
            "Acima de 30% → aviso de margem insuficiente para novos compromissos."
        ),
        ge=0.0, le=1.0,
    )

    # ── /accounts ─────────────────────────────────────────────────────

    sazonalidade_receita: Optional[list[float]] = Field(
        default=None,
        description=(
            "Multiplicadores mensais de receita (12 valores, índice 0 = Janeiro). "
            "1.0 = mês médio. Ex: 1.4 em Dezembro (13º salário). "
            "Usado para identificar meses de baixa renda onde a parcela pode ser crítica."
        ),
        min_length=12,
        max_length=12,
    )
    meses_consecutivos_poupanca: Optional[int] = Field(
        default=None,
        description=(
            "Número de meses consecutivos com saldo positivo (receita > despesa). "
            "< 3 meses → aviso se o orçamento declarado for alto."
        ),
        ge=0,
    )

    # ── /financings ───────────────────────────────────────────────────

    experiencia_financiamento: Optional[bool] = Field(
        default=None,
        description=(
            "True se o usuário já tem ou teve financiamentos. "
            "Reduz incerteza sobre aprovação bancária e CET praticado."
        ),
    )
    cet_historico_real: Optional[float] = Field(
        default=None,
        description=(
            "CET anual médio real cobrado em financiamentos anteriores (decimal). "
            "Mais preciso que cet_medio_historico para estimar o custo de um novo "
            "financiamento — exclui crédito pessoal e consignado."
        ),
        ge=0.0, le=2.0,
    )


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

    risk_score: Optional[float] = Field(
        default=None,
        description=(
            "Score contínuo de tolerância ao risco [0-1], computado pelo RiskScorer "
            "a partir do histórico. None quando calculado por declaração direta do usuário "
            "ou quando transactions_df não está disponível. "
            "Alimenta thresholds interpolados no StrategyEngine."
        ),
        ge=0.0,
        le=1.0,
    )

    risk_score_confidence: Optional[float] = Field(
        default=None,
        description=(
            "Confiança do RiskScore [0-1]. "
            "Propagada pelo ArchitectService a partir do RiskScorer.confidence. "
            "Alimenta o confidence_score base do StrategyEngine em vez do valor fixo 0.85."
        ),
        ge=0.0,
        le=1.0,
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

    expected_rental_income: Optional[float] = Field(
        default=None,
        description=(
            "Renda de aluguel mensal estimada pelo usuário (R$). "
            "Quando informado junto com asset_type=IMOVEL, ativa o plano de "
            "alavancagem: usar o aluguel para cobrir (parcialmente ou totalmente) "
            "as parcelas do consórcio ou financiamento."
        ),
        gt=0,
    )

    transaction_costs_pct: Optional[float] = Field(
        default=None,
        description=(
            "Custos de transação como percentual do target_amount (ex: 0.04 = 4%). "
            "Inclui ITBI (2-3%), cartório, registro e avaliação. "
            "Somado ao custo total de FINANCING e CONSORTIUM para imóvel. "
            "Padrão usado quando None e asset_type=IMOVEL: 0.04 (4%)."
        ),
        ge=0.0,
        le=0.15,
    )

    # Renda mensal do usuário — usada pelo M3.3 (card_optimization_bonus)
    # e pelo BudgetAdvisor para calcular comprometimento de renda.
    monthly_income: Optional[float] = Field(
        default=None,
        description="Renda mensal bruta do usuário (R$). Melhora a precisão do card_optimization_bonus.",
        gt=0,
    )

    # ── Open Finance — fonte primária de dados personalizados ─────────

    open_finance_features: Optional[OpenFinanceFeatures] = Field(
        default=None,
        description=(
            "Features extraídas dos endpoints do Open Finance Brasil (/investments, "
            "/loans, /accounts, /financings). Quando presentes, substituem os valores "
            "genéricos de mercado por dados reais do usuário: rendimento_real_atual "
            "substitui CDI teórico, cet_historico_real substitui CET médio de mercado. "
            "confidence_score base sobe para 0.95 (dados reais eliminam suposições)."
        ),
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


class BreakevenDistribution(BaseModel):
    """
    Distribuição do CET de break-even sob incerteza macroeconômica.

    O break-even não é um ponto fixo: quando as taxas de juros variam (SELIC/CDI),
    o custo de oportunidade do SAVE_INVEST muda, deslocando o CET de equilíbrio.
    Esta classe quantifica essa incerteza via N cenários amostrados.

    Attributes:
        cet_p10:              10% dos cenários têm break-even abaixo deste CET.
                              O financiamento é vantajoso em quase todos os cenários
                              se o CET atual estiver abaixo deste valor.
        cet_p50:              Break-even mediano (cenário central).
        cet_p90:              90% dos cenários têm break-even abaixo deste CET.
        prob_financing_wins:  P(break-even > CET atual) — probabilidade de que
                              financiar seja melhor que poupar/investir dado o CET corrente.
        n_simulations:        Cenários válidos (descartados: target já coberto pela entrada).
    """

    cet_p10: float = Field(..., description="Percentil 10 do CET de break-even (decimal anual)")
    cet_p50: float = Field(..., description="Mediana do CET de break-even (decimal anual)")
    cet_p90: float = Field(..., description="Percentil 90 do CET de break-even (decimal anual)")
    prob_financing_wins: float = Field(
        ...,
        description=(
            "Fração dos cenários em que financiar supera poupar/investir ao CET atual. "
            "Ex: 0.73 → 'Em 73%% dos cenários projetados, financiar é mais vantajoso.'"
        ),
        ge=0.0,
        le=1.0,
    )
    n_simulations: int = Field(..., description="Número de cenários macroeconômicos simulados", ge=1)


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
    financing_rental: Optional[float] = Field(
        default=None,
        description="NPV do financiamento + aluguel (R$). None se não calculado.",
    )
    consortium_selic_rental: Optional[float] = Field(
        default=None,
        description="NPV do consórcio + SELIC + aluguel (R$). None se não calculado.",
    )
    break_even_cet: Optional[float] = Field(
        default=None,
        description=(
            "Taxa CET anual (decimal) a partir da qual SAVE_INVEST supera FINANCING. "
            "Ex: 0.1320 = acima de 13,2% a.a. o financiamento fica mais caro que investir. "
            "None quando não foi possível calcular (ex: SAVE_INVEST já é sempre melhor)."
        ),
    )
    breakeven_distribution: Optional[BreakevenDistribution] = Field(
        default=None,
        description=(
            "Distribuição probabilística do break-even CET sob incerteza macroeconômica. "
            "Captura como a variação de SELIC/CDI desloca o ponto de equilíbrio. "
            "None para método SAC ou quando o cálculo falha."
        ),
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


class CardOptimizationBonus(BaseModel):
    """
    M3.3 — Retorno de cartão de crédito sobre as parcelas do financiamento.

    O Architect cruza com o Optimizer (F2) para mostrar quanto o usuário
    pode recuperar em pontos/cashback ao pagar as parcelas no melhor
    cartão disponível, reduzindo o custo efetivo do financiamento.

    Presente apenas quando recommended_strategy == FINANCING.
    """

    best_card_name: str = Field(
        ...,
        description="Nome ou descrição do cartão simulado",
    )
    pts_per_brl: float = Field(
        ...,
        description="Pontos por R$ gasto no cartão (ex: 2.0 = 2 pts/R$)",
        ge=0,
    )
    point_value_brl: float = Field(
        ...,
        description="Valor de cada ponto em R$ (ex: 0.016 = R$ 0,016/ponto para milhas)",
        ge=0,
    )
    monthly_bonus_brl: float = Field(
        ...,
        description="Retorno financeiro estimado por mês (R$)",
        ge=0,
    )
    annual_bonus_brl: float = Field(
        ...,
        description="Retorno financeiro estimado por ano (R$)",
        ge=0,
    )
    total_bonus_brl: float = Field(
        ...,
        description="Retorno total ao longo de todo o financiamento (R$)",
        ge=0,
    )
    effective_cost_reduction_pct: float = Field(
        ...,
        description="Redução percentual no custo total do financiamento (ex: 3.2 = 3,2%)",
        ge=0,
    )
    narrative: str = Field(
        ...,
        description="Frase explicativa em linguagem natural para o usuário",
        min_length=10,
        max_length=400,
    )
    liquidity_risk: str = Field(
        default="SAFE",
        description="Risco de liquidez do melhor cartão (SAFE | WARNING | HIGH | CRITICAL), "
                    "conforme avaliação do Optimizer.",
    )


class RentalLeveragePlan(BaseModel):
    """
    Plano de alavancagem por aluguel para aquisição de imóvel via consórcio ou financiamento.

    Quando o usuário informa expected_rental_income, o Architect calcula se e quanto
    o aluguel cobre as parcelas, reduzindo o custo efetivo da aquisição.

    Attributes:
        monthly_rental_income:  Renda de aluguel mensal estimada (R$).
        monthly_payment:        Parcela mensal da estratégia recomendada (R$).
        rental_coverage_pct:    Quanto % da parcela o aluguel cobre (ex: 72.5 = 72,5%).
        monthly_out_of_pocket:  Desembolso real mensal do usuário = parcela − aluguel (R$).
                                Zero ou negativo = aluguel cobre tudo (sobra).
        total_rental_income:    Total acumulado de aluguel no período (R$).
        net_acquisition_cost:   Custo líquido real = custo_total − total_rental_income (R$).
        is_self_sustaining:     True se aluguel ≥ parcela (imóvel se paga sozinho).
        months_covered:         Quantidade de meses em que o aluguel cobre a parcela inteira.
        narrative:              Explicação em linguagem natural para o usuário.
    """

    monthly_rental_income: float = Field(
        ..., description="Renda de aluguel mensal estimada (R$)", ge=0
    )
    monthly_payment: float = Field(
        ..., description="Parcela mensal da estratégia recomendada (R$)", ge=0
    )
    rental_coverage_pct: float = Field(
        ..., description="% da parcela coberta pelo aluguel (ex: 72.5 = 72,5%)", ge=0
    )
    monthly_out_of_pocket: float = Field(
        ...,
        description=(
            "Desembolso real mensal do usuário após deduzir o aluguel (R$). "
            "Negativo = aluguel supera a parcela (gera renda extra)."
        ),
    )
    total_rental_income: float = Field(
        ..., description="Total acumulado de aluguel no período (R$)", ge=0
    )
    net_acquisition_cost: float = Field(
        ...,
        description=(
            "Custo líquido real da aquisição = custo_total − total_rental_income (R$). "
            "Representa quanto o imóvel custou de fato considerando o aluguel recebido."
        ),
    )
    is_self_sustaining: bool = Field(
        ...,
        description="True se aluguel ≥ parcela (o imóvel se paga sozinho com o aluguel).",
    )
    months_covered: int = Field(
        ...,
        description="Meses em que o aluguel cobre 100% da parcela",
        ge=0,
    )
    narrative: str = Field(
        ...,
        description="Explicação do plano de alavancagem em linguagem natural",
        min_length=20,
        max_length=500,
    )


class CompoundStrategyLeg(BaseModel):
    """
    Resultado detalhado de uma estratégia composta (Estratégia 4 ou 5).

    Presente em SimulationResponse.compound_strategies quando
    asset_type=IMOVEL e expected_rental_income foi informado.

    Estratégia 4 — FINANCING_RENTAL:
        Financiamento bancário cujo custo mensal líquido é reduzido pelo aluguel.
        monthly_selic_contribution = 0.0

    Estratégia 5 — CONSORTIUM_SELIC_RENTAL:
        Consórcio onde a entrada é investida na SELIC enquanto aguarda contemplação.
        Aluguel + rendimento SELIC cobrem (total ou parcialmente) as parcelas.

    Attributes:
        strategy_type:              Tipo da estratégia composta
        monthly_gross_payment:      Parcela bruta (sem descontar aluguel), R$
        monthly_rental_income:      Renda de aluguel mensal estimada, R$
        monthly_selic_contribution: Rendimento SELIC mensal sobre a entrada (só Estratégia 5), R$
        monthly_net_cost:           Desembolso real mensal = parcela − aluguel − SELIC, R$
        total_gross_cost:           Custo total bruto da estratégia base (sem aluguel), R$
        total_rental_income:        Total acumulado de aluguel no período, R$
        net_acquisition_cost:       Custo líquido real = total_gross_cost − total_rental_income, R$
        npv:                        Valor presente líquido do fluxo composto (SELIC como desconto), R$
        months:                     Prazo relevante (financiamento ou contemplação esperada)
        is_self_sustaining:         True se aluguel + SELIC cobrem 100% das parcelas sem aporte
        narrative:                  Explicação em linguagem natural
    """

    strategy_type: StrategyType = Field(
        ..., description="Tipo da estratégia composta"
    )
    monthly_gross_payment: float = Field(
        ..., description="Parcela bruta (antes de descontar aluguel), R$", ge=0
    )
    monthly_rental_income: float = Field(
        ..., description="Renda de aluguel mensal estimada, R$", ge=0
    )
    monthly_selic_contribution: float = Field(
        default=0.0,
        description="Rendimento SELIC mensal sobre a entrada investida (Estratégia 5), R$",
        ge=0,
    )
    monthly_net_cost: float = Field(
        ...,
        description="Desembolso real mensal após aluguel e SELIC (R$). Zero = auto-sustentável.",
        ge=0,
    )
    total_gross_cost: float = Field(
        ..., description="Custo total bruto da estratégia base (R$)", ge=0
    )
    total_rental_income: float = Field(
        ..., description="Total acumulado de aluguel no período (R$)", ge=0
    )
    net_acquisition_cost: float = Field(
        ...,
        description=(
            "Custo líquido real da aquisição = total_gross_cost − total_rental_income (R$). "
            "Pode ser negativo se o aluguel superar o custo total."
        ),
    )
    npv: float = Field(
        ...,
        description=(
            "NPV do fluxo composto usando SELIC como desconto. "
            "Mais alto (menos negativo) = melhor. Auto-sustentável → NPV próximo de 0 ou positivo."
        ),
    )
    months: int = Field(
        ..., description="Prazo relevante em meses", ge=1
    )
    is_self_sustaining: bool = Field(
        ...,
        description="True se aluguel + SELIC cobrem 100% das parcelas em todos os meses.",
    )
    narrative: str = Field(
        ...,
        description="Explicação da estratégia composta em linguagem natural",
        min_length=20,
        max_length=500,
    )


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
# EFICIÊNCIA — SEGUNDA RECOMENDAÇÃO (equilíbrio custo × tempo × liquidez)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EfficiencyAnalysis(BaseModel):
    """
    Estratégia com melhor equilíbrio entre perda de capital, velocidade e orçamento.

    Score (0.0–1.0) composto por três dimensões:
      - capital_loss (40%): quanto se paga além do valor do bem (juros/taxas).
        SAVE_INVEST = 0%, CONSORTIUM = ~15–20%, FINANCING = 30–80%.
      - speed       (35%): velocidade de posse (meses). Menor = melhor.
      - budget      (25%): parcela / orçamento mensal. Menor = melhor.

    O campo readiness_flag indica se o usuário está financeiramente pronto para
    esta aquisição considerando orçamento, perda de capital e perfil de risco.

    Presente em SimulationResponse.efficient_strategy apenas quando difere de
    recommended_strategy, evitando duplicidade.

    Attributes:
        strategy_type:         Estratégia com maior efficiency_score.
        efficiency_score:      Score composto (0.0 = pior, 1.0 = perfeito).
        capital_loss_pct:      Extra pago além do valor do bem, em % (ex: 18.5 = 18,5%).
        months_to_acquire:     Meses até ter a posse do bem.
        budget_commitment_pct: Parcela mensal como % do orçamento (ex: 62.0 = 62%).
        monthly_payment:       Parcela mensal absoluta (R$).
        total_cost:            Custo total esperado desta estratégia (R$).
        readiness_flag:        PRONTO / ATENCAO / AGUARDAR — prontidão financeira.
        rationale:             Explicação em linguagem natural (inclui aviso se AGUARDAR).
    """

    strategy_type: StrategyType = Field(
        ..., description="Estratégia com maior efficiency_score"
    )
    efficiency_score: float = Field(
        ..., description="Score de eficiência composto (0.0–1.0)", ge=0.0, le=1.0
    )
    capital_loss_pct: float = Field(
        ...,
        description=(
            "Extra pago além do valor do bem em % (ex: 18.5 = 18,5%). "
            "SAVE_INVEST = 0%. Menor = melhor."
        ),
        ge=0.0,
    )
    months_to_acquire: int = Field(
        ..., description="Meses até a posse do bem", ge=1
    )
    budget_commitment_pct: float = Field(
        ...,
        description=(
            "Parcela mensal como % do orçamento máximo (ex: 62.0 = 62%). "
            "Acima de 100% indica parcela fora do orçamento."
        ),
        ge=0.0,
    )
    monthly_payment: float = Field(
        ..., description="Parcela mensal desta estratégia (R$)", ge=0
    )
    total_cost: float = Field(
        ..., description="Custo total esperado desta estratégia (R$)", ge=0
    )
    readiness_flag: str = Field(
        default="PRONTO",
        description=(
            "Prontidão financeira para esta aquisição: "
            "PRONTO = parcela e custo dentro do confortável para o perfil; "
            "ATENCAO = viável mas exige disciplina (parcela entre 35–60% do orçamento "
            "ou perda de capital 80–120%); "
            "AGUARDAR = ainda não é a hora — parcela acima de 60% do orçamento ou custo "
            "excessivo para o perfil declarado."
        ),
    )
    rationale: str = Field(
        ...,
        description="Justificativa em linguagem natural (inclui aviso de timing se AGUARDAR)",
        min_length=20,
        max_length=500,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIMULAÇÃO MACROECONÔMICA CORRELACIONADA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StrategyMacroStats(BaseModel):
    """
    Distribuição de NPV de uma estratégia sob N cenários macroeconômicos.

    P10/P50/P90: percentis da distribuição de NPVs.
    cvar_95: CVaR ao nível 95% — NPV médio nos 5% piores cenários.
             Quanto mais negativo, maior o risco de cauda.
    """

    npv_p10: float = Field(..., description="Percentil 10 do NPV (R$) — cenário pessimista")
    npv_p50: float = Field(..., description="Mediana do NPV (R$) — caso central estocástico")
    npv_p90: float = Field(..., description="Percentil 90 do NPV (R$) — cenário otimista")
    cvar_95: float = Field(
        ...,
        description=(
            "CVaR ao nível 95% (R$): NPV esperado nos 5% piores cenários macroeconômicos. "
            "Mais negativo = maior risco de cauda para esta estratégia."
        ),
    )


class MacroSimulationResult(BaseModel):
    """
    Resultado da simulação de cenários macroeconômicos correlacionados.

    Gerado via VAR(1) com Cholesky: modela a correlação histórica entre Selic,
    IPCA e valorização de ativos. Cada trajetória usa taxas variando mês a mês,
    capturando riscos que o NPV determinístico ignora.

    Attributes:
        n_simulations:  Número de trajetórias simuladas.
        distributions:  Estatísticas de NPV por estratégia (P10/P50/P90 + CVaR95).
        prob_best:      P(esta estratégia tem o melhor NPV) — dicionário que soma 1.0.
                        Estratégia com maior prob_best é a mais robusta a cenários macro.
    """

    n_simulations: int = Field(..., description="Número de trajetórias macroeconômicas simuladas", ge=1)

    distributions: Dict[str, StrategyMacroStats] = Field(
        ...,
        description=(
            "Distribuição de NPVs por estratégia. "
            "Chaves: 'FINANCING', 'SAVE_INVEST', 'CONSORTIUM' (quando aplicável)."
        ),
    )

    prob_best: Dict[str, float] = Field(
        ...,
        description=(
            "Probabilidade de cada estratégia ter o melhor NPV no conjunto de cenários. "
            "Soma 1.0. Ex: {'FINANCING': 0.23, 'SAVE_INVEST': 0.61, 'CONSORTIUM': 0.16}."
        ),
    )

    ssd_matrix: Optional[Dict[str, Dict[str, str]]] = Field(
        default=None,
        description=(
            "Dominância Estocástica de Segunda Ordem par a par. "
            "ssd_matrix[A][B] = 'dominates' | 'dominated' | 'inconclusive'. "
            "'dominates': A é preferível a B para qualquer agente avesso a risco."
        ),
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

    # ── M3.3 — Custo de oportunidade cruzado F3↔F2 ─────────────────

    card_optimization_bonus: Optional[CardOptimizationBonus] = Field(
        default=None,
        description=(
            "M3.3 — Retorno de cartão sobre as parcelas do financiamento. "
            "Presente apenas quando recommended_strategy=FINANCING. "
            "Mostra quanto o usuário pode recuperar em pontos/cashback "
            "ao pagar as parcelas no melhor cartão disponível."
        ),
    )

    # ── Plano de alavancagem por aluguel (imóvel) ────────────────────

    rental_leverage_plan: Optional[RentalLeveragePlan] = Field(
        default=None,
        description=(
            "Plano de alavancagem por aluguel. Presente quando asset_type=IMOVEL "
            "e expected_rental_income foi informado. Mostra quanto o aluguel cobre "
            "das parcelas e o custo líquido real da aquisição."
        ),
    )

    # ── Estratégias compostas (imóvel + aluguel) ─────────────────────

    compound_strategies: Optional[list[CompoundStrategyLeg]] = Field(
        default=None,
        description=(
            "Estratégias compostas calculadas quando asset_type=IMOVEL e "
            "expected_rental_income foi informado. Contém FINANCING_RENTAL e/ou "
            "CONSORTIUM_SELIC_RENTAL com seus NPVs e análise de auto-sustentabilidade. "
            "None se asset_type != IMOVEL ou expected_rental_income não informado."
        ),
    )

    # ── Alavancagem otimizada (imóvel + aluguel + consórcio aumentado) ─

    leverage_analysis: Optional[dict] = Field(
        default=None,
        description=(
            "LeverageOptimizer: testa consórcios de 1.2x–3.0x o valor do imóvel. "
            "Presente quando asset_type=IMOVEL e expected_rental_income informado. "
            "Indica se é possível que aluguel + SELIC paguem as parcelas sozinhos "
            "(patrimônio 'de graça'). Inclui multiplicador ótimo e patrimônio final."
        ),
    )

    # ── Custos de transação aplicados ────────────────────────────────

    transaction_costs_applied: Optional[float] = Field(
        default=None,
        description=(
            "Custos de transação somados ao custo total (ITBI, cartório, registro, etc.). "
            "Presente quando transaction_costs_pct foi informado na request."
        ),
    )

    # ── Custo anual de manutenção ─────────────────────────────────────

    maintenance_cost_annual: Optional[float] = Field(
        default=None,
        description=(
            "Custo anual estimado de manutenção do bem (R$). "
            "IMOVEL: 1% do valor do imóvel/ano (reparos, IPTU, condomínio mínimo). "
            "VEICULO: R$ 1.000/ano (revisões, pneus, IPVA implícito). "
            "Incluído no custo total (expected_cost / max_cost) das estratégias de "
            "aquisição imediata (FINANCING, CONSORTIUM). None para outros tipos de bem."
        ),
    )

    # ── Estratégia mais eficiente (segunda recomendação) ─────────────

    efficient_strategy: Optional["EfficiencyAnalysis"] = Field(
        default=None,
        description=(
            "Estratégia com melhor equilíbrio entre perda de capital, velocidade de "
            "aquisição e impacto no orçamento. Presente apenas quando difere de "
            "recommended_strategy. Ex: recommended=SAVE_INVEST (ótimo financeiro), "
            "efficient_strategy=CONSORTIUM (menor perda que FINANCING, posse em 24–36 meses)."
        ),
    )

    # ── Simulação macroeconômica correlacionada ───────────────────────

    macro_simulation: Optional["MacroSimulationResult"] = Field(
        default=None,
        description=(
            "Resultado da simulação de cenários macroeconômicos correlacionados (VAR-1). "
            "Modela Selic, IPCA e valorização do ativo com correlações históricas. "
            "Fornece distribuição de NPVs (P10/P50/P90), CVaR95 e probabilidade de cada "
            "estratégia ser a melhor sob incerteza macro. None quando n_simulations=0 "
            "ou ocorreu erro na simulação."
        ),
    )

    ssd_guarantee: Optional[str] = Field(
        default=None,
        description=(
            "Garantia matemática da recomendação via dominância estocástica de 2ª ordem. "
            "Presente quando a estratégia recomendada domina todas as outras para qualquer "
            "agente avesso a risco, independente do grau de aversão. "
            "Ex: 'FINANCING domina SAVE_INVEST e CONSORTIUM em SSD'. "
            "None quando o resultado é inconclusivo entre estratégias."
        ),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# M3.4 — TIMING SCENARIO: "E SE EU ESPERAR?"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TimingScenario(BaseModel):
    """
    Resultado de simular esperar W meses antes de comprar (M3.4).

    Ao esperar, o usuário acumula mais entrada, reduzindo o principal
    financiado e a parcela mensal. Este modelo captura o custo desse
    timing: quanto da recomendação muda e qual a economia potencial.

    Attributes:
        wait_months:              Meses de espera antes da compra (0 = comprar agora).
        accumulated_down_payment: Entrada original + poupança mensal × meses.
        new_principal:            target_amount − nova entrada (valor financiado reduzido).
        recommended_strategy:     Melhor estratégia para este cenário.
        total_cost_expected:      Custo total esperado (R$).
        total_cost_npv:           Custo total em valor presente (NPV) — para comparar cenários.
        monthly_payment:          Nova parcela mensal após aumento da entrada.
        saving_vs_now:            Economia vs comprar agora (>0 = cenário melhor que agora).
        comparison_text:          Texto comparativo em linguagem natural.
    """

    wait_months: int = Field(
        ...,
        description="Meses de espera antes da compra (0 = comprar agora)",
        ge=0,
        le=120,
    )
    accumulated_down_payment: float = Field(
        ...,
        description="Entrada disponível após espera: original + mensal × meses (R$)",
        ge=0,
    )
    new_principal: float = Field(
        ...,
        description="Valor efetivamente financiado após aumento da entrada (R$)",
        ge=0,
    )
    recommended_strategy: StrategyType = Field(
        ...,
        description="Estratégia recomendada para este cenário de timing",
    )
    total_cost_expected: float = Field(
        ...,
        description="Custo total esperado do cenário (R$)",
        ge=0,
    )
    total_cost_npv: float = Field(
        ...,
        description="NPV do custo total do cenário — usado para comparar com outros timing",
    )
    monthly_payment: float = Field(
        ...,
        description="Parcela mensal da estratégia para este cenário (R$)",
        ge=0,
    )
    saving_vs_now: float = Field(
        ...,
        description=(
            "Economia vs comprar agora (R$). "
            "Positivo = esperar é melhor. Negativo = comprar agora é melhor."
        ),
    )
    comparison_text: str = Field(
        ...,
        description="Descrição comparativa do cenário em linguagem natural",
        min_length=10,
        max_length=400,
    )



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
    # Open Finance
    "OpenFinanceFeatures",
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
    "CardOptimizationBonus",
    "RentalLeveragePlan",
    "CompoundStrategyLeg",
    "EfficiencyAnalysis",
    # Simulação macroeconômica
    "StrategyMacroStats",
    "MacroSimulationResult",
    # Response
    "SimulationResponse",
    # M3.4 — Timing
    "TimingScenario",
    # Persistência
    "SimulationReport",
]

# Resolver forward references (EfficiencyAnalysis referenciado em SimulationResponse)
SimulationResponse.model_rebuild()
