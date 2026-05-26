# app/core/recurrence.py
import polars as pl
from typing import List, Dict


def detect_recurring(transactions: List[Dict]) -> List[Dict]:
    """
    Detecta receitas e despesas recorrentes com base em frequência mensal.

    Heurística:
      - Mesmo valor aproximado
      - Mesmo nome normalizado
      - Frequência >= 2 meses

    Retorna:
      Lista de padrões recorrentes detectados
    """
    if not transactions:
        return []

    df = pl.DataFrame(transactions)

    if df.is_empty():
        return []

    # Normalize date column: accept both `date` and `transaction_date` incoming names
    if "date" in df.columns:
        df = df.with_columns([pl.col("date").cast(pl.Date).alias("date")])
    elif "transaction_date" in df.columns:
        df = df.with_columns([pl.col("transaction_date").cast(pl.Date).alias("date")])
    else:
        # No usable date column — nothing to detect
        return []

    # Normalize description: prefer `description`, fallback to `description_raw`
    desc_col = "description" if "description" in df.columns else (
        "description_raw" if "description_raw" in df.columns else None
    )
    if desc_col:
        df = df.with_columns([
            pl.col(desc_col).str.to_lowercase().str.strip_chars().alias("description"),
        ])
    else:
        # ensure description exists as empty strings to avoid failures
        df = df.with_columns([pl.lit("").alias("description")])

    df = df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))

    grouped = (
        df.group_by(["description", "amount"])
        .agg([
            pl.col("month").n_unique().alias("months"),
            pl.len().alias("total_occurrences"),
        ])
        .filter(pl.col("months") >= 2)
    )

    return [
        {
            "description": row["description"],
            "amount": float(row["amount"]),
            "months": int(row["months"]),
            "occurrences": int(row["total_occurrences"]),
        }
        for row in grouped.to_dicts()
    ]


class RecurringDetector:
    """
    Detector de transações recorrentes (assinaturas e parcelamentos).
    Encapsula o motor principal de recorrência do core.

    Aceita Polars DataFrame ou List[Dict] como entrada.
    Retorna Polars DataFrame com os padrões detectados.
    """

    _EMPTY_SCHEMA = {
        "description": pl.Utf8,
        "amount": pl.Float64,
        "months": pl.Int64,
        "occurrences": pl.Int64,
    }

    def run(self, df) -> pl.DataFrame:
        _empty = pl.DataFrame(schema=self._EMPTY_SCHEMA)

        transactions = df.to_dicts() if hasattr(df, "to_dicts") else df

        try:
            patterns = detect_recurring(transactions)
        except (KeyError, TypeError, ValueError):
            return _empty

        return pl.DataFrame(patterns) if patterns else _empty
