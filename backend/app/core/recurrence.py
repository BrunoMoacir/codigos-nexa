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
