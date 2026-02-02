# app/etl/shadow_invoices/subscription_detector.py

import polars as pl
from app.etl.shadow_invoices.base import ShadowInvoiceDetector


class SubscriptionDetector(ShadowInvoiceDetector):

    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return pl.DataFrame()

        df = df.with_columns([
            pl.col("transaction_date").dt.truncate("1mo").alias("month")
        ])

        grouped = (
            df.group_by("description")
            .agg([
                pl.col("amount").mean().alias("avg_amount"),
                pl.col("amount").std().alias("std_amount"),
                pl.col("month").unique().count().alias("months")
            ])
            .filter(
                (pl.col("months") >= 3) &
                (pl.col("std_amount") <= pl.col("avg_amount") * 0.05)
            )
        )

        if grouped.is_empty():
            return pl.DataFrame()

        today = df.select(pl.col("transaction_date").max()).item()

        return grouped.select([
            pl.lit("SUBSCRIPTION").alias("type"),
            pl.col("avg_amount").alias("amount"),
            (pl.lit(today) + pl.duration(days=30)).alias("next_due_date"),
            pl.struct(["description", "months"]).alias("metadata"),
            pl.lit(0.9).alias("confidence")
        ])
