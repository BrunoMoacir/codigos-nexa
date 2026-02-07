"""
app/schemas/__init__.py - Entry Point do Módulo Schemas

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Exporta todos os schemas Pydantic do sistema para facilitar imports.

╔══════════════════════════════════════════════════════════════════════╗
║ COMO USAR                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

# ✅ Import limpo (recomendado):
from app.schemas import (
    ShadowInvoiceResponse,
    CashflowProjectionResponse,
    SafeToSpendResponse
)

# ❌ Import verboso (evitar):
from app.schemas.shadow_invoice import ShadowInvoiceResponse
from app.schemas.cashflow import CashflowProjectionResponse
from app.schemas.safe_to_spend import SafeToSpendResponse
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - SHADOW INVOICES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .shadow_invoice import (
    ShadowInvoiceResponse,
    ShadowInvoiceListResponse,
    convert_shadow_df_to_response
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - CASHFLOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .cashflow import (
    CashflowProjectionPoint,
    CashflowSummaryResponse,
    CashflowProjectionResponse,
    convert_cashflow_to_response,
    convert_projection_summary_to_response
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - SAFE TO SPEND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .safe_to_spend import (
    SafeToSpendResponse,
    SafeToSpendDetailedResponse,
    convert_safe_to_spend_to_basic_response,
    convert_safe_to_spend_to_detailed_response,
    convert_safe_to_spend
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - FORECAST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .forecast import (
    FinancialHealthResponse,
    MonthlyForecastResponse,
    ForecastResponse,
    convert_user_profile_to_health,
    build_forecast_response
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - TRANSACTION (JÁ EXISTENTE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .transaction import (
    TransactionWebhook,
    TransactionBatchResult,
    RejectedTransaction,
    TransactionOut  # Se existir
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS - ENUMS (JÁ EXISTENTE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .enums import (
    TransactionType,
    TransactionStatus,
    CategoryType
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SHADOW INVOICES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "ShadowInvoiceResponse",
    "ShadowInvoiceListResponse",
    "convert_shadow_df_to_response",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASHFLOW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "CashflowProjectionPoint",
    "CashflowSummaryResponse",
    "CashflowProjectionResponse",
    "convert_cashflow_to_response",
    "convert_projection_summary_to_response",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SAFE TO SPEND
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "SafeToSpendResponse",
    "SafeToSpendDetailedResponse",
    "convert_safe_to_spend_to_basic_response",
    "convert_safe_to_spend_to_detailed_response",
    "convert_safe_to_spend",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FORECAST
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "FinancialHealthResponse",
    "MonthlyForecastResponse",
    "ForecastResponse",
    "convert_user_profile_to_health",
    "build_forecast_response",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TRANSACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "TransactionCreate",
    "TransactionResponse",
    "TransactionBatchCreate",
    "TransactionBatchResponse",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ENUMS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "TransactionType",
    "TransactionStatus",
    "CategoryType",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# METADATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__version__ = "1.0.0"
__author__ = "Nexa AI Team"
__status__ = "Production"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIM DO ARQUIVO __init__.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
📦 RESUMO DO MÓDULO SCHEMAS (v1.0.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCHEMAS DISPONÍVEIS:
    1. Shadow Invoices    → Obrigações futuras (assinaturas + parcelamentos)
    2. Cashflow           → Projeção de fluxo de caixa
    3. Safe-to-Spend      → Cálculo de gastos seguros
    4. Forecast           → Previsões financeiras consolidadas
    5. Transactions       → Transações financeiras
    6. Enums              → Tipos e categorias

CONVERSORES:
    • convert_shadow_df_to_response()           → Polars → Shadow Invoice
    • convert_cashflow_to_response()            → Polars → Cashflow
    • convert_projection_summary_to_response()  → Dataclass → Cashflow
    • convert_safe_to_spend()                   → Dataclass → Safe-to-Spend
    • convert_user_profile_to_health()          → Dataclass → Financial Health
    • build_forecast_response()                 → Builder → Forecast

EXEMPLO DE USO:
    >>> from app.schemas import (
    ...     ShadowInvoiceResponse,
    ...     CashflowProjectionResponse,
    ...     SafeToSpendResponse,
    ...     ForecastResponse
    ... )
    >>> 
    >>> # Usar em endpoints FastAPI
    >>> @app.get("/forecast", response_model=ForecastResponse)
    >>> async def get_forecast():
    ...     return forecast_response
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""