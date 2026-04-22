"""
TemporalDetector — extrai padrões temporais de gasto para personalizar
o timing de notificações e recomendações.

Usa apenas `date` (sem `hour_of_day`), pois o campo de hora não está disponível
no transactions_clean que chega ao optimizer.
"""

from __future__ import annotations
import polars as pl


class TemporalDetector:

    def analyze(self, df: pl.DataFrame) -> dict:
        _empty = {
            "peak_spend_day_of_month": None,
            "peak_spend_day_of_week": None,
            "is_weekend_spender": False,
            "spending_pattern": "IRREGULAR",
            "best_notification_day": 5,
        }

        if df.is_empty():
            return _empty

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return _empty

        by_day = (
            expenses
            .with_columns(pl.col("date").dt.day().alias("dom"))
            .group_by("dom")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .sort("total", descending=True)
        )
        peak_day = int(by_day[0]["dom"][0]) if len(by_day) > 0 else 1

        by_weekday = (
            expenses
            .with_columns(pl.col("date").dt.weekday().alias("dow"))
            .group_by("dow")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .sort("total", descending=True)
        )
        peak_weekday = int(by_weekday[0]["dow"][0]) if len(by_weekday) > 0 else 0

        total_spend = float(expenses["amount"].sum()) * -1
        weekend_spend = float(
            expenses.filter(pl.col("date").dt.weekday() >= 5)["amount"].sum()
        ) * -1
        is_weekend_spender = (weekend_spend / total_spend) > 0.45 if total_spend > 0 else False

        monthly_totals = (
            expenses
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().abs())
        )
        if len(monthly_totals) >= 2:
            mean = float(monthly_totals["amount"].mean())
            std = float(monthly_totals["amount"].std())
            cv = std / mean if mean > 0 else 1.0
            spending_pattern = "REGULAR" if cv < 0.15 else "MODERADO" if cv < 0.35 else "IRREGULAR"
        else:
            spending_pattern = "SEM_DADOS"

        best_notification_day = max(1, peak_day - 3)

        return {
            "peak_spend_day_of_month": peak_day,
            "peak_spend_day_of_week": peak_weekday,
            "is_weekend_spender": is_weekend_spender,
            "spending_pattern": spending_pattern,
            "best_notification_day": best_notification_day,
        }
