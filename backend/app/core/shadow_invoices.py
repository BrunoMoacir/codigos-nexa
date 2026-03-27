# app/core/shadow_invoices.py
import polars as pl
import re
from typing import List, Dict


def normalize_merchant(desc: str) -> str:
    desc = desc.lower()
    desc = re.sub(r"(www\.)|(\.com)|(\.br)|(\.net)|(\.io)", "", desc)
    desc = re.sub(r"\d+", "", desc)
    desc = re.sub(r"[^a-z\s]", " ", desc)

    blacklist = ["compra", "pagamento", "debito", "credito", "recorrente", "assinatura"]
    for word in blacklist:
        desc = desc.replace(word, "")

    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def detect_shadow_invoices(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return []

    df = pl.DataFrame(transactions)

    if df.is_empty():
        return []

    df = df.with_columns(
        pl.col("date").cast(pl.Date).alias("date"),
    )
    df = df.with_columns(
        pl.col("date").dt.truncate("1mo").alias("month"),
    )

    df = (
        df.filter(pl.col("amount") < 0)
        .with_columns(pl.col("amount").abs().alias("abs_amount"))
        .filter(pl.col("abs_amount") <= 100)
        .with_columns(
            pl.col("description")
            .map_elements(normalize_merchant, return_dtype=pl.Utf8)
            .alias("merchant")
        )
    )

    grouped = (
        df.group_by("merchant")
        .agg([
            pl.col("month").n_unique().alias("months"),
            pl.col("abs_amount").mean().alias("avg_amount"),
            pl.len().alias("occurrences"),
        ])
        .filter(pl.col("months") >= 3)
    )

    return [
        {
            "description": row["merchant"],
            "avg_amount": round(float(row["avg_amount"]), 2),
            "months": int(row["months"]),
            "occurrences": int(row["occurrences"]),
        }
        for row in grouped.to_dicts()
    ]


class ShadowInvoiceDetector:
    """
    Detector de shadow invoices (cobranças ocultas/esquecidas).
    Encapsula o motor principal de shadow invoices do core.

    Aceita Polars DataFrame ou List[Dict] como entrada.
    Retorna Polars DataFrame com os suspects detectados.
    """

    _EMPTY_SCHEMA = {
        "description": pl.Utf8,
        "avg_amount": pl.Float64,
        "months": pl.Int64,
        "occurrences": pl.Int64,
    }

    def run(self, transactions) -> pl.DataFrame:
        _empty = pl.DataFrame(schema=self._EMPTY_SCHEMA)

        data = transactions.to_dicts() if hasattr(transactions, "to_dicts") else transactions
        results = detect_shadow_invoices(data)

        return pl.DataFrame(results) if results else _empty
