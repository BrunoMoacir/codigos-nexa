"""
app/negotiator/models.py — Schemas do F13: Negotiator Bot

Tipos de entrada e saída do detector de oportunidades e gerador de scripts.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class NegotiationTrigger(str, Enum):
    JUROS_ROTATIVO_ALTO  = "JUROS_ROTATIVO_ALTO"   # pagou juros acima do CDI nos últimos 3 meses
    ANUIDADE_ALTA        = "ANUIDADE_ALTA"           # anuidade do cartão acima da média de mercado
    HEALTH_SCORE_ALTO    = "HEALTH_SCORE_ALTO"       # score >= 60 — usuário tem poder de barganha


class NegotiationChannel(str, Enum):
    APP_CHAT   = "APP_CHAT"    # chat no app do banco (gera registro escrito)
    TELEFONE   = "TELEFONE"    # ligação para o gerente
    AGENCIA    = "AGENCIA"     # visita presencial
    EMAIL      = "EMAIL"       # e-mail ao gerente de relacionamento


class NegotiationOpportunity(BaseModel):
    """Oportunidade de negociação detectada para um banco/produto."""
    trigger: NegotiationTrigger
    bank_name: str
    product: str                                    # "Crédito Rotativo", "Anuidade Cartão", etc.

    # Situação atual do usuário
    user_rate_monthly: Optional[float] = Field(
        default=None,
        description="Taxa mensal estimada que o usuário paga (ex: 0.12 = 12% a.m.)",
    )
    user_fee_monthly: Optional[float] = Field(
        default=None,
        description="Valor médio mensal pago em tarifas deste produto (R$)",
    )

    # Referência de mercado
    market_rate_monthly: Optional[float] = Field(
        default=None,
        description="Taxa média de mercado para o mesmo produto (ex: 0.035 = 3.5% a.m.)",
    )
    potential_saving_monthly: float = Field(
        default=0.0,
        description="Economia mensal estimada se conseguir taxa de mercado (R$)",
    )

    # Contexto do usuário para argumentação
    health_score: int = Field(ge=0, le=100)
    months_as_good_payer: int = Field(
        default=0,
        description="Meses consecutivos sem juros rotativos detectados (proxy de bom pagador)",
    )
    description: str = ""                           # resumo legível da oportunidade


class NegotiationScript(BaseModel):
    """Roteiro de negociação gerado pelo Claude."""
    opportunity: NegotiationOpportunity

    # Roteiro em linguagem natural
    opening_line: str           # frase de abertura para iniciar a negociação
    key_arguments: list[str]    # argumentos principais a usar (3-5 bullet points)
    target_ask: str             # o que pedir objetivamente (ex: "redução da taxa para X%")
    fallback_ask: str           # pedido alternativo se recusar o principal
    closing_line: str           # como encerrar a conversa

    # Logística
    recommended_channel: NegotiationChannel
    best_time: str              # ex: "terça ou quarta-feira, manhã (9h-11h)"
    estimated_success_pct: int = Field(ge=0, le=100, description="Probabilidade estimada de sucesso (0-100)")

    # Metadados
    generated_by: str = "claude-sonnet-4-6"
    warnings: list[str] = Field(default_factory=list)


class NegotiationRequest(BaseModel):
    """Entrada do endpoint POST /negotiator/generate-script."""
    user_id: str
    bank_name: Optional[str] = Field(
        default=None,
        description="Banco específico para negociar. Se None, detecta automaticamente.",
    )

    model_config = {"json_schema_extra": {
        "example": {
            "user_id": "user_123",
            "bank_name": "Itaú",
        }
    }}


class NegotiationReport(BaseModel):
    """Resposta completa do endpoint."""
    user_id: str
    opportunities_found: int
    scripts: list[NegotiationScript]
    summary: str                                    # texto resumido para o agente
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
