# app/forecast/schemas.py
# Consolidated schemas for the forecast feature (F1)
# Re-exports from individual schema modules for backward compatibility

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

from app.forecast.schemas_shadow_invoice import (
    ShadowInvoiceResponse,
    ShadowInvoiceListResponse,
    convert_shadow_df_to_response,
)

from app.forecast.schemas_forecast import (
    FinancialHealthResponse,
    MonthlyForecastResponse,
    ForecastResponse,
    build_forecast_response,
)

__all__ = [
    # Cashflow
    "CashflowProjectionPoint",
    "CashflowSummaryResponse",
    "CashflowProjectionResponse",
    "convert_cashflow_to_response",
    "convert_projection_summary_to_response",
    # Safe to spend
    "SafeToSpendResponse",
    "SafeToSpendDetailedResponse",
    "convert_safe_to_spend_to_basic_response",
    "convert_safe_to_spend_to_detailed_response",
    "convert_safe_to_spend",
    # Shadow invoice
    "ShadowInvoiceResponse",
    "ShadowInvoiceListResponse",
    "convert_shadow_df_to_response",
    # Forecast
    "FinancialHealthResponse",
    "MonthlyForecastResponse",
    "ForecastResponse",
    "build_forecast_response",
]
