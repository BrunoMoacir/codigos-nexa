import polars as pl
from app.etl.shadow_invoices.runner import run_shadow_invoice_detection

df = pl.DataFrame({
    "transaction_id": [1,2,3,4,5,6],
    "description": ["Netflix", "Netflix", "Netflix", "Amazon Parcelado", "Amazon Parcelado", "Amazon Parcelado"],
    "amount": [-39.9, -39.9, -39.9, -120.0, -120.0, -120.0],
    "transaction_date": pl.date_range(
        start=pl.date(2025, 7, 1),
        end=pl.date(2025, 12, 1),
        interval="1mo",
        eager=True
    )
})

result = run_shadow_invoice_detection(df)
print(result)
