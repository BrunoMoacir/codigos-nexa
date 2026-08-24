"""
app/schemas/shadow_invoice.py - Schemas para Shadow Invoices

RESPONSABILIDADE:
    Schemas Pydantic para obrigações futuras detectadas pelo sistema
    (assinaturas e parcelamentos)

INTEGRAÇÃO:
    - Usado pelos endpoints de Shadow Invoices
    - Retornado por run_shadow_invoice_detection()
    - Consumido pelo CashflowProjector

USAGE:
    from app.forecast.schemas_shadow_invoice import (
        ShadowInvoiceResponse,
        ShadowInvoiceListResponse
    )
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Literal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHADOW INVOICE (Individual)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ShadowInvoiceResponse(BaseModel):
    """
    Schema de uma shadow invoice detectada.
    
    Representa uma obrigação futura identificada pelo sistema
    (assinatura ou parcelamento).
    
    Attributes:
        type: Tipo da obrigação (SUBSCRIPTION ou INSTALLMENT)
        description: Descrição da transação original
        amount: Valor (negativo para débito)
        next_due_date: Próxima data de vencimento
        confidence: Confiança da detecção (0.0-1.0)
        occurrences: Quantas vezes foi detectado historicamente
        installment_info: Info de parcelamento (ex: "3/12")
        metadata: Dados adicionais (opcional)
    
    Example:
        >>> invoice = ShadowInvoiceResponse(
        ...     type="SUBSCRIPTION",
        ...     description="NETFLIX.COM *ASSINATURA PREMIUM",
        ...     amount=-49.90,
        ...     next_due_date=datetime(2026, 3, 5),
        ...     confidence=0.92,
        ...     occurrences=6,
        ...     installment_info=None,
        ...     metadata={"category": "Lazer"}
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "SUBSCRIPTION",
                "description": "NETFLIX.COM *ASSINATURA PREMIUM",
                "amount": -49.90,
                "next_due_date": "2026-03-05T00:00:00Z",
                "confidence": 0.92,
                "occurrences": 6,
                "installment_info": None,
                "metadata": {"category": "Lazer"}
            }
        }
    )
    
    type: Literal["SUBSCRIPTION", "INSTALLMENT"] = Field(
        ...,
        description="Tipo da obrigação futura"
    )
    
    description: str = Field(
        ...,
        description="Descrição da transação original",
        min_length=1,
        max_length=500
    )
    
    amount: float = Field(
        ...,
        description="Valor da obrigação (negativo para débito)",
        lt=0.0  # Deve ser negativo
    )
    
    next_due_date: datetime = Field(
        ...,
        description="Próxima data de vencimento esperada"
    )
    
    confidence: float = Field(
        ...,
        description="Confiança da detecção (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    
    occurrences: int | None = Field(
        None,
        description="Quantas vezes foi detectado no histórico",
        ge=0
    )
    
    installment_info: str | None = Field(
        None,
        description="Informação de parcelamento (ex: '3/12')",
        pattern=r"^\d+/\d+$"  # Valida formato "N/M"
    )
    
    metadata: dict | None = Field(
        None,
        description="Dados adicionais (categoria, frequência, etc)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHADOW INVOICE LIST (Coleção)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ShadowInvoiceListResponse(BaseModel):
    """
    Lista de shadow invoices com metadados agregados.
    
    Attributes:
        invoices: Lista de shadow invoices detectadas
        total_count: Quantidade total de obrigações
        total_monthly_impact: Impacto total mensal (soma dos amounts)
        subscriptions_count: Quantidade de assinaturas
        installments_count: Quantidade de parcelamentos
    
    Example:
        >>> response = ShadowInvoiceListResponse(
        ...     invoices=[invoice1, invoice2, invoice3],
        ...     total_count=12,
        ...     total_monthly_impact=-1068.10,
        ...     subscriptions_count=9,
        ...     installments_count=3
        ... )
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invoices": [
                    {
                        "type": "SUBSCRIPTION",
                        "description": "NETFLIX.COM *ASSINATURA PREMIUM",
                        "amount": -49.90,
                        "next_due_date": "2026-03-05T00:00:00Z",
                        "confidence": 0.92,
                        "occurrences": 6,
                        "installment_info": None,
                        "metadata": {"category": "Lazer"}
                    },
                    {
                        "type": "INSTALLMENT",
                        "description": "COMPRA PARCELADA 7/12 - CELULAR SAMSUNG",
                        "amount": -249.90,
                        "next_due_date": "2026-03-10T00:00:00Z",
                        "confidence": 0.90,
                        "occurrences": 6,
                        "installment_info": "7/12",
                        "metadata": {"remaining": 6}
                    }
                ],
                "total_count": 12,
                "total_monthly_impact": -1068.10,
                "subscriptions_count": 9,
                "installments_count": 3
            }
        }
    )
    
    invoices: list[ShadowInvoiceResponse] = Field(
        ...,
        description="Lista de shadow invoices detectadas"
    )
    
    total_count: int = Field(
        ...,
        description="Quantidade total de obrigações",
        ge=0
    )
    
    total_monthly_impact: float = Field(
        ...,
        description="Impacto total mensal (soma dos amounts)",
        le=0.0  # Deve ser negativo ou zero
    )
    
    subscriptions_count: int = Field(
        0,
        description="Quantidade de assinaturas detectadas",
        ge=0
    )
    
    installments_count: int = Field(
        0,
        description="Quantidade de parcelamentos detectados",
        ge=0
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSOR: Polars DataFrame → Pydantic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_shadow_df_to_response(
    shadow_df: "pl.DataFrame"  # type: ignore
) -> ShadowInvoiceListResponse:
    """
    Converte DataFrame de Shadow Invoices para Pydantic response.
    
    Args:
        shadow_df: DataFrame retornado por run_shadow_invoice_detection()
            Colunas esperadas:
            - type (str)
            - amount (float)
            - next_due_date (datetime)
            - metadata (dict)
            - confidence (float)
    
    Returns:
        ShadowInvoiceListResponse pronto para serialização JSON
    
    Example:
        >>> from app.subscriptions.shadow_invoices import run_shadow_invoice_detection
        >>> shadow_df = run_shadow_invoice_detection(df)
        >>> response = convert_shadow_df_to_response(shadow_df)
        >>> print(response.total_count)
        12
    """
    import polars as pl
    
    if shadow_df.is_empty():
        return ShadowInvoiceListResponse(
            invoices=[],
            total_count=0,
            total_monthly_impact=0.0,
            subscriptions_count=0,
            installments_count=0
        )
    
    # Converter cada row para ShadowInvoiceResponse
    invoices = []
    
    for row in shadow_df.iter_rows(named=True):
        # Extrair metadata
        metadata_dict = row.get("metadata", {})
        
        invoice = ShadowInvoiceResponse(
            type=row["type"],
            description=metadata_dict.get("description", "Unknown"),
            amount=float(row["amount"]),
            next_due_date=row["next_due_date"],
            confidence=float(row["confidence"]),
            occurrences=metadata_dict.get("occurrences"),
            installment_info=metadata_dict.get("installment_info"),
            metadata=metadata_dict
        )
        
        invoices.append(invoice)
    
    # Calcular agregados
    total_count = len(invoices)
    total_monthly_impact = float(shadow_df["amount"].sum())
    
    subscriptions_count = shadow_df.filter(
        pl.col("type") == "SUBSCRIPTION"
    ).height
    
    installments_count = shadow_df.filter(
        pl.col("type") == "INSTALLMENT"
    ).height
    
    return ShadowInvoiceListResponse(
        invoices=invoices,
        total_count=total_count,
        total_monthly_impact=total_monthly_impact,
        subscriptions_count=subscriptions_count,
        installments_count=installments_count
    )