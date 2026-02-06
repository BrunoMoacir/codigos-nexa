#backend/app/core/forecast.py
import polars as pl
from datetime import date, timedelta


def generate_daily_forecast(
    transactions: pl.DataFrame,
    start_balance: float,
    days: int = 90
) -> pl.DataFrame:
    """
    Gera saldo projetado dia a dia.
    """

    # 🔒 Normalização defensiva do tipo de data
    if transactions.schema.get("date") != pl.Date:
        transactions = transactions.with_columns(
            pl.col("date").str.strptime(pl.Date, strict=False)
        )

    today = date.today()
    future_dates = [today + timedelta(days=i) for i in range(days)]

    df_future = pl.DataFrame({"date": future_dates})

    daily = (
        transactions
        .group_by("date")
        .agg(pl.col("amount").sum().alias("daily_amount"))
    )

    forecast = (
        df_future
        .join(daily, on="date", how="left")
        .with_columns(pl.col("daily_amount").fill_null(0))
        .with_columns(
            pl.col("daily_amount").cum_sum().alias("delta")
        )
        .with_columns(
            (pl.lit(start_balance) + pl.col("delta")).alias("projected_balance")
        )
    )

    return forecast


def calculate_safe_to_spend(
    forecast: pl.DataFrame,
    buffer: float = 1000.0,
    days: int = 30
) -> dict:
    """
    Calcula Safe-to-Spend com base no forecast projetado.
    """

    horizon = forecast.head(days)

    min_balance = horizon["projected_balance"].min()

    safe_total = min_balance - buffer
    safe_total = max(0.0, safe_total)

    safe_daily = safe_total / days if days > 0 else 0.0

    return {
        "days": days,
        "buffer": buffer,
        "min_projected_balance": float(min_balance),
        "safe_to_spend_total": float(safe_total),
        "safe_to_spend_daily": float(safe_daily),
    }
