import polars as pl

from app.cashflow.projector import CashflowProjector


def test_cashflow_projection():
    projector = CashflowProjector()

    df = pl.DataFrame({
        "transaction_date": ["2026-02-01", "2026-02-05"],
        "amount": [-500, 3000]
    }).with_columns(
        pl.col("transaction_date").str.to_date()
    )

    shadow = pl.DataFrame({
        "transaction_date": ["2026-02-10"],
        "next_due_date": ["2026-02-10"],
        "amount": [-800],
        "type": ["subscription"]
    }).with_columns(
        pl.col("transaction_date").str.to_date(),
        pl.col("next_due_date").str.to_date()
    )

    forecast = projector.project(
        transactions_df=df,
        shadow_invoices_df=shadow,
        current_balance=1000
    )

    assert not forecast.is_empty()
    assert "projected_balance" in forecast.columns
