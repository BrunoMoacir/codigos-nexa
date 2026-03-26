"""
app/schemas/safe_to_spend.py - Schemas para Safe-to-Spend

RESPONSABILIDADE:
    Schemas Pydantic para cálculos de quanto o usuário pode gastar
    com segurança sem comprometer obrigações futuras

INTEGRAÇÃO:
    - Usado pelos endpoints de Safe-to-Spend
    - Retornado por SafeToSpendCalculator
    - Consumido pelo frontend para alertas

USAGE:
    from app.schemas.safe_to_spend import (
        SafeToSpendResponse,
        SafeToSpendDetailedResponse
    )
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE TO SPEND (Básico)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SafeToSpendResponse(BaseModel):
    """
    Schema básico de safe-to-spend.
    
    Resposta simplificada com apenas os valores principais.
    
    Attributes:
        safe_to_spend_total: Valor total seguro para gastar
        safe_to_spend_daily: Valor médio diário seguro
        days: Período considerado
        risk_level: Classificação de risco
    
    Example:
        >>> response = SafeToSpendResponse(
        ...     safe_to_spend_total=1320.00,
        ...     safe_to_spend_daily=44.00,
        ...     days=30,
        ...     risk_level="LOW"
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "safe_to_spend_total": 1320.00,
                "safe_to_spend_daily": 44.00,
                "days": 30,
                "risk_level": "LOW"
            }
        }
    )
    
    safe_to_spend_total: float = Field(
        ...,
        description="Valor total que pode gastar com segurança",
        ge=0.0
    )
    
    safe_to_spend_daily: float = Field(
        ...,
        description="Valor médio diário que pode gastar",
        ge=0.0
    )
    
    days: int = Field(
        ...,
        description="Período considerado (dias)",
        ge=1,
        le=365
    )
    
    risk_level: RiskLevel = Field(
        ...,
        description="Classificação de risco financeiro"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE TO SPEND (Detalhado)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SafeToSpendDetailedResponse(BaseModel):
    """
    Schema detalhado de safe-to-spend.
    
    Resposta completa com breakdown de cálculos e métricas intermediárias.
    
    Attributes:
        current_balance: Saldo atual
        min_projected_balance: Menor saldo projetado no período
        total_shadow_invoices: Impacto total das shadow invoices
        safety_buffer: Buffer de segurança aplicado
        safe_to_spend_total: Valor total seguro
        safe_to_spend_daily: Valor diário seguro
        days: Período considerado
        risk_level: Classificação de risco
        safety_buffer_pct: Percentual de buffer usado
        recommendations: Recomendações baseadas no risco
    
    Example:
        >>> response = SafeToSpendDetailedResponse(
        ...     current_balance=5000.00,
        ...     min_projected_balance=3700.00,
        ...     total_shadow_invoices=-1068.10,
        ...     safety_buffer=200.00,
        ...     safe_to_spend_total=1320.00,
        ...     safe_to_spend_daily=44.00,
        ...     days=30,
        ...     risk_level="LOW",
        ...     safety_buffer_pct=15.0,
        ...     recommendations=[]
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_balance": 5000.00,
                "min_projected_balance": 3700.00,
                "total_shadow_invoices": -1068.10,
                "safety_buffer": 200.00,
                "safe_to_spend_total": 1320.00,
                "safe_to_spend_daily": 44.00,
                "days": 30,
                "risk_level": "LOW",
                "safety_buffer_pct": 15.0,
                "recommendations": [
                    "Você está em boa situação financeira",
                    "Continue monitorando suas assinaturas"
                ]
            }
        }
    )
    
    current_balance: float = Field(
        ...,
        description="Saldo atual (último conhecido)"
    )
    
    min_projected_balance: float = Field(
        ...,
        description="Menor saldo projetado no período"
    )
    
    total_shadow_invoices: float = Field(
        ...,
        description="Impacto total das shadow invoices",
        le=0.0  # Deve ser negativo ou zero
    )
    
    safety_buffer: float = Field(
        ...,
        description="Buffer de segurança aplicado",
        ge=0.0
    )
    
    safe_to_spend_total: float = Field(
        ...,
        description="Valor total que pode gastar com segurança",
        ge=0.0
    )
    
    safe_to_spend_daily: float = Field(
        ...,
        description="Valor médio diário que pode gastar",
        ge=0.0
    )
    
    days: int = Field(
        ...,
        description="Período considerado (dias)",
        ge=1,
        le=365
    )
    
    risk_level: RiskLevel = Field(
        ...,
        description="Classificação de risco financeiro"
    )
    
    safety_buffer_pct: float = Field(
        ...,
        description="Percentual de buffer usado (%)",
        ge=0.0,
        le=100.0
    )
    
    recommendations: list[str] = Field(
        default_factory=list,
        description="Recomendações baseadas no risco"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSOR: SafeToSpendResult (dataclass) → Pydantic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_safe_to_spend_to_basic_response(
    result: "SafeToSpendResult"  # type: ignore (from app.cashflow.safe_to_spend)
) -> SafeToSpendResponse:
    """
    Converte SafeToSpendResult para SafeToSpendResponse (básico).
    
    Args:
        result: SafeToSpendResult retornado por SafeToSpendCalculator
    
    Returns:
        SafeToSpendResponse com campos essenciais
    
    Example:
        >>> from app.cashflow import SafeToSpendCalculator
        >>> 
        >>> calculator = SafeToSpendCalculator()
        >>> result = calculator.calculate(projection_df, 30)
        >>> 
        >>> response = convert_safe_to_spend_to_basic_response(result)
    """
    return SafeToSpendResponse(
        safe_to_spend_total=result.safe_to_spend_total,
        safe_to_spend_daily=result.safe_to_spend_daily,
        days=result.days,
        risk_level=result.risk_level
    )


def convert_safe_to_spend_to_detailed_response(
    result: "SafeToSpendResult",  # type: ignore
    safety_buffer_pct: float = 15.0
) -> SafeToSpendDetailedResponse:
    """
    Converte SafeToSpendResult para SafeToSpendDetailedResponse (completo).
    
    Args:
        result: SafeToSpendResult retornado por SafeToSpendCalculator
        safety_buffer_pct: Percentual de buffer usado (padrão: 15%)
    
    Returns:
        SafeToSpendDetailedResponse com todos os detalhes
    
    Example:
        >>> from app.cashflow import SafeToSpendCalculator
        >>> 
        >>> calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
        >>> result = calculator.calculate(projection_df, 30)
        >>> 
        >>> response = convert_safe_to_spend_to_detailed_response(result, 15.0)
    """
    # Gerar recomendações baseadas no risco
    recommendations = _generate_recommendations(result.risk_level)
    
    return SafeToSpendDetailedResponse(
        current_balance=result.current_balance,
        min_projected_balance=result.min_projected_balance,
        total_shadow_invoices=result.total_shadow_invoices,
        safety_buffer=result.safety_buffer,
        safe_to_spend_total=result.safe_to_spend_total,
        safe_to_spend_daily=result.safe_to_spend_daily,
        days=result.days,
        risk_level=result.risk_level,
        safety_buffer_pct=safety_buffer_pct,
        recommendations=recommendations
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Gerar Recomendações
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _generate_recommendations(risk_level: RiskLevel) -> list[str]:
    """
    Gera recomendações baseadas no nível de risco.
    
    Args:
        risk_level: Classificação de risco
    
    Returns:
        Lista de recomendações em português
    """
    recommendations_map = {
        "LOW": [
            "✅ Você está em boa situação financeira",
            "Continue monitorando suas assinaturas para evitar gastos desnecessários",
            "Considere investir a sobra do mês"
        ],
        "MEDIUM": [
            "⚠️ Atenção moderada necessária",
            "Evite gastos não essenciais este mês",
            "Revise suas assinaturas e parcelamentos",
            "Crie uma reserva de emergência se possível"
        ],
        "HIGH": [
            "🚨 Risco alto de saldo negativo",
            "URGENTE: Reduza gastos imediatamente",
            "Cancele assinaturas não essenciais",
            "Evite novos parcelamentos",
            "Busque fontes alternativas de renda se possível"
        ],
        "CRITICAL": [
            "🔴 SITUAÇÃO CRÍTICA: Risco iminente",
            "AÇÃO IMEDIATA: Seu saldo pode ficar negativo em breve",
            "Cancele TODAS as assinaturas não essenciais",
            "NÃO faça novos gastos",
            "Contate seu banco para evitar taxas de saldo negativo",
            "Busque ajuda financeira urgente se necessário"
        ]
    }
    
    return recommendations_map.get(risk_level, [])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Wrapper Simplificado
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_safe_to_spend(
    result: "SafeToSpendResult",  # type: ignore
    detailed: bool = False,
    safety_buffer_pct: float = 15.0
) -> SafeToSpendResponse | SafeToSpendDetailedResponse:
    """
    Converte SafeToSpendResult para o schema apropriado.
    
    Wrapper que decide qual conversor usar baseado no parâmetro `detailed`.
    
    Args:
        result: SafeToSpendResult do calculador
        detailed: Se True, retorna versão detalhada
        safety_buffer_pct: Percentual de buffer (para versão detalhada)
    
    Returns:
        SafeToSpendResponse (básico) ou SafeToSpendDetailedResponse (completo)
    
    Example:
        >>> # Básico
        >>> response = convert_safe_to_spend(result)
        >>> 
        >>> # Detalhado
        >>> response = convert_safe_to_spend(result, detailed=True)
    """
    if detailed:
        return convert_safe_to_spend_to_detailed_response(result, safety_buffer_pct)
    else:
        return convert_safe_to_spend_to_basic_response(result)