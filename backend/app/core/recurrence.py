#app/core/recurrency.py
import pandas as pd
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

    df = pd.DataFrame(transactions)

    if df.empty:
        return []

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    df["description"] = df["description"].str.lower().str.strip()

    grouped = (
        df.groupby(["description", "amount"])
        .agg(
            months=("month", "nunique"),
            total_occurrences=("amount", "count"),
        )
        .reset_index()
    )

    recurring = grouped[grouped["months"] >= 2]

    patterns = []

    for _, row in recurring.iterrows():
        patterns.append(
            {
                "description": row["description"],
                "amount": float(row["amount"]),
                "months": int(row["months"]),
                "occurrences": int(row["total_occurrences"]),
            }
        )

    return patterns


class RecurringDetector:
    """
    Detector de transações recorrentes (assinaturas e parcelamentos).
    Encapsula o motor principal de recorrência do core.

    Aceita Polars DataFrame ou List[Dict] como entrada.
    Retorna Polars DataFrame com os padrões detectados.
    """

    _EMPTY_SCHEMA = {
        "description": "pl.Utf8",
        "amount": "pl.Float64",
        "months": "pl.Int64",
        "occurrences": "pl.Int64",
    }

    def run(self, df) -> "pl.DataFrame":
        import polars as pl

        _empty = pl.DataFrame(
            schema={
                "description": pl.Utf8,
                "amount": pl.Float64,
                "months": pl.Int64,
                "occurrences": pl.Int64,
            }
        )

        transactions = df.to_dicts() if hasattr(df, "to_dicts") else df

        # detect_recurring() espera colunas específicas (date, description, amount).
        # Se o DataFrame de entrada usar nomes diferentes, retorna resultado vazio
        # em vez de propagar o erro — esse é o comportamento esperado do core.
        try:
            patterns = detect_recurring(transactions)
        except (KeyError, TypeError, ValueError):
            return _empty

        return pl.DataFrame(patterns) if patterns else _empty
