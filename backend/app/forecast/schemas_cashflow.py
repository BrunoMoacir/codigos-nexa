"""
app/schemas/cashflow.py - Schemas para Projeção de Cashflow

RESPONSABILIDADE:
    Schemas Pydantic para projeções de fluxo de caixa e análise de risco

INTEGRAÇÃO:
    - Usado pelos endpoints de Cashflow
    - Retornado por CashflowProjector
    - Consumido pelo frontend para gráficos

MUDANÇAS v2.1:
    ✅ CORRIGIDO: Conflito de nome "date" (campo vs tipo)
    ✅ Campo renomeado: "date" → "projection_date"
    ✅ Compatível com CashflowProjector atualizado

USAGE:
    from app.schemas.cashflow import (
        CashflowProjectionPoint,
        CashflowProjectionResponse,
        CashflowSummaryResponse
    )
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import date as DateType  # ✅ IMPORT com alias para evitar conflito
from typing import Literal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASHFLOW PROJECTION POINT (Ponto Individual)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CashflowProjectionPoint(BaseModel):
    """
    Um ponto na projeção de cashflow (dia específico).
    
    Representa o estado financeiro projetado para um dia específico.
    
    Attributes:
        projection_date: Data do ponto de projeção (✅ renomeado de "date")
        projected_balance: Saldo projetado para este dia
        expenses: Débito do dia (shadow invoices)
        risk_flag: Flag de risco se saldo negativo
    
    Example:
        >>> point = CashflowProjectionPoint(
        ...     projection_date=date(2026, 3, 5),
        ...     projected_balance=4950.10,
        ...     expenses=-49.90,
        ...     risk_flag=None
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "projection_date": "2026-03-05",
                "projected_balance": 4950.10,
                "expenses": -49.90,
                "risk_flag": None
            }
        }
    )
    
    projection_date: DateType = Field(  # ✅ Usa DateType (alias de date)
        ...,
        description="Data da projeção"
    )
    
    projected_balance: float = Field(
        ...,
        description="Saldo projetado para este dia"
    )
    
    expenses: float = Field(  # ✅ Renomeado de "shadow_amount"
        0.0,
        description="Débito do dia (shadow invoices)",
        le=0.0  # Deve ser negativo ou zero
    )
    
    risk_flag: Literal["NEGATIVE_BALANCE"] | None = Field(
        None,
        description="Flag de risco (presente se saldo negativo)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASHFLOW SUMMARY (Resumo Agregado)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CashflowSummaryResponse(BaseModel):
    """
    Resumo agregado da projeção de cashflow.
    
    Contém métricas consolidadas da projeção (sem dados diários).
    
    Attributes:
        horizon_days: Período projetado (dias)
        starting_balance: Saldo inicial
        ending_balance: Saldo final projetado
        worst_balance: Menor saldo atingido
        negative_day: Primeiro dia com saldo negativo (None se nunca)
        risk_level: Classificação de risco
        total_shadow_impact: Impacto total das shadow invoices
        days_at_risk: Quantidade de dias com saldo negativo
    
    Example:
        >>> summary = CashflowSummaryResponse(
        ...     horizon_days=30,
        ...     starting_balance=5000.00,
        ...     ending_balance=3809.69,
        ...     worst_balance=3809.69,
        ...     negative_day=None,
        ...     risk_level="LOW",
        ...     total_shadow_impact=-1068.10,
        ...     days_at_risk=0
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "horizon_days": 30,
                "starting_balance": 5000.00,
                "ending_balance": 3809.69,
                "worst_balance": 3809.69,
                "negative_day": None,
                "risk_level": "LOW",
                "total_shadow_impact": -1068.10,
                "days_at_risk": 0
            }
        }
    )
    
    horizon_days: int = Field(
        ...,
        description="Período projetado em dias",
        ge=1,
        le=365
    )
    
    starting_balance: float = Field(
        ...,
        description="Saldo inicial (último conhecido)"
    )
    
    ending_balance: float = Field(
        ...,
        description="Saldo final projetado"
    )
    
    worst_balance: float = Field(
        ...,
        description="Menor saldo atingido no período"
    )
    
    negative_day: int | None = Field(
        None,
        description="Primeiro dia com saldo negativo (None se nunca)",
        ge=1
    )
    
    risk_level: RiskLevel = Field(
        ...,
        description="Classificação de risco financeiro"
    )
    
    total_shadow_impact: float = Field(
        ...,
        description="Impacto total das shadow invoices",
        le=0.0  # Deve ser negativo ou zero
    )
    
    days_at_risk: int = Field(
        0,
        description="Quantidade de dias com saldo negativo",
        ge=0
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASHFLOW PROJECTION (Resposta Completa)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CashflowProjectionResponse(BaseModel):
    """
    Resposta completa da projeção de cashflow.
    
    Contém tanto o resumo agregado quanto a projeção diária detalhada.
    
    Attributes:
        summary: Resumo com métricas agregadas
        daily_projection: Projeção dia a dia (lista de pontos)
    
    Example:
        >>> response = CashflowProjectionResponse(
        ...     summary=summary,
        ...     daily_projection=[point1, point2, point3, ...]
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "summary": {
                    "horizon_days": 30,
                    "starting_balance": 5000.00,
                    "ending_balance": 3809.69,
                    "worst_balance": 3809.69,
                    "negative_day": None,
                    "risk_level": "LOW",
                    "total_shadow_impact": -1068.10,
                    "days_at_risk": 0
                },
                "daily_projection": [
                    {
                        "projection_date": "2026-02-07",
                        "projected_balance": 5000.00,
                        "expenses": 0.0,
                        "risk_flag": None
                    },
                    {
                        "projection_date": "2026-02-10",
                        "projected_balance": 4950.10,
                        "expenses": -49.90,
                        "risk_flag": None
                    }
                ]
            }
        }
    )
    
    summary: CashflowSummaryResponse = Field(
        ...,
        description="Resumo agregado da projeção"
    )
    
    daily_projection: list[CashflowProjectionPoint] = Field(
        ...,
        description="Projeção dia a dia (lista ordenada por data)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSOR: Polars DataFrame → Pydantic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_cashflow_to_response(
    projection_df: "pl.DataFrame",  # type: ignore
    summary_data: dict
) -> CashflowProjectionResponse:
    """
    Converte DataFrame de projeção para Pydantic response.
    
    Args:
        projection_df: DataFrame retornado por CashflowProjector.project()
            Colunas esperadas:
            - date (date) ✅ coluna do Polars
            - projected_balance (float)
            - expenses (float)
            - risk_flag (str | None)
        
        summary_data: Dict com métricas agregadas
            Chaves esperadas:
            - horizon_days, starting_balance, ending_balance,
              worst_balance, negative_day, risk_level,
              total_shadow_impact
    
    Returns:
        CashflowProjectionResponse pronto para serialização JSON
    
    Example:
        >>> from app.cashflow import CashflowProjector
        >>> 
        >>> projector = CashflowProjector(horizon_days=30)
        >>> projection_df = projector.project(df, shadow_df)
        >>> 
        >>> # Converter para response
        >>> response = convert_cashflow_to_response(
        ...     projection_df,
        ...     summary.to_dict()
        ... )
    """
    import polars as pl
    
    # Converter DataFrame para lista de pontos
    daily_projection = []
    
    for row in projection_df.iter_rows(named=True):
        point = CashflowProjectionPoint(
            projection_date=row["date"],  # ✅ Campo "date" do Polars → "projection_date" do schema
            projected_balance=float(row["projected_balance"]),
            expenses=float(row["expenses"]),
            risk_flag=row.get("risk_flag")
        )
        daily_projection.append(point)
    
    # Calcular days_at_risk
    days_at_risk = projection_df.filter(
        pl.col("risk_flag").is_not_null()
    ).height
    
    # Criar summary
    summary = CashflowSummaryResponse(
        horizon_days=summary_data["horizon_days"],
        starting_balance=summary_data["starting_balance"],
        ending_balance=summary_data["ending_balance"],
        worst_balance=summary_data["worst_balance"],
        negative_day=summary_data.get("negative_day"),
        risk_level=summary_data["risk_level"],
        total_shadow_impact=summary_data["total_shadow_impact"],
        days_at_risk=days_at_risk
    )
    
    return CashflowProjectionResponse(
        summary=summary,
        daily_projection=daily_projection
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Converter ProjectionSummary (dataclass) → Response
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_projection_summary_to_response(
    projection_df: "pl.DataFrame",  # type: ignore
    summary: "ProjectionSummary"  # type: ignore (from app.cashflow.projector)
) -> CashflowProjectionResponse:
    """
    Converte ProjectionSummary (dataclass) para CashflowProjectionResponse.
    
    Versão simplificada que aceita o dataclass ProjectionSummary diretamente.
    
    Args:
        projection_df: DataFrame da projeção
        summary: ProjectionSummary retornado por get_summary()
    
    Returns:
        CashflowProjectionResponse
    
    Example:
        >>> from app.cashflow import project_cashflow
        >>> 
        >>> projection_df, summary = project_cashflow(df, shadow_df, 30)
        >>> response = convert_projection_summary_to_response(projection_df, summary)
    """
    return convert_cashflow_to_response(
        projection_df,
        summary.to_dict()
    )