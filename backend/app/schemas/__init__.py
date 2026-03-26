# app/schemas/__init__.py
# LEGACY COMPATIBILITY LAYER
# Schemas have moved to app.forecast.schemas and app.core.schemas

from app.forecast.schemas_shadow_invoice import (
    ShadowInvoiceResponse,
    ShadowInvoiceListResponse,
    convert_shadow_df_to_response,
)

from app.forecast.schemas_cashflow import (
    CashflowProjectionPoint,
    CashflowSummaryResponse,
    CashflowProjectionResponse,
    convert_cashflow_to_response,
    convert_projection_summary_to_response,
)

from app.forecast.schemas_safe_to_spend import (
    SafeToSpendResponse,
    SafeToSpendDetailedResponse,
    convert_safe_to_spend_to_basic_response,
    convert_safe_to_spend_to_detailed_response,
    convert_safe_to_spend,
)

from app.forecast.schemas_forecast import (
    ForecastResponse,
    build_forecast_response,
)

from app.core.schemas.transaction import (
    TransactionWebhook,
    TransactionBatchResult,
)

from app.core.schemas.enums import (
    BankTier,
    DataStatus,
)
