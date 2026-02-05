import polars as pl
from datetime import timedelta

def detect_recurring_transactions(df: pl.DataFrame) -> pl.DataFrame:
    """
    Marca transações recorrentes (mensal, semanal).
    """

    df = df.with_columns([
        pl.col("date").cast(pl.Date)
    ])

    grouped = (
        df.group_by(["description", "amount"])
        .agg([
            pl.count().alias("count"),
            pl.col("date").min().alias("first_date"),
            pl.col("date").max().alias("last_date")
        ])
        .filter(pl.col("count") >= 3)
    )

    recurring_keys = grouped.select(["description", "amount"])

    return (
        df.join(recurring_keys, on=["description", "amount"], how="left")
          .with_columns(
              pl.when(pl.col("description").is_not_null())
              .then(True)
              .otherwise(False)
              .alias("is_recurring")
          )
    )
