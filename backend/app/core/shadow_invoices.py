import pandas as pd
from typing import List, Dict


def detect_shadow_invoices(transactions: List[Dict]) -> List[Dict]:
    """
    Detecta possíveis cobranças invisíveis:
      - Débitos recorrentes pequenos
      - Valores baixos
      - Frequência mensal

    Heurística:
      - valor absoluto <= 100
      - frequência >= 3 meses
      - descrição semelhante
    """

    if not transactions:
        return []

    df = pd.DataFrame(transactions)

    if df.empty:
        return []

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    df["description"] = df["description"].str.lower().str.strip()

    df = df[df["amount"] < 0]
    df["abs_amount"] = df["amount"].abs()

    df = df[df["abs_amount"] <= 100]

    grouped = (
        df.groupby(["description"])
        .agg(
            months=("month", "nunique"),
            avg_amount=("abs_amount", "mean"),
            occurrences=("abs_amount", "count"),
        )
        .reset_index()
    )

    suspects = grouped[grouped["months"] >= 3]

    results = []

    for _, row in suspects.iterrows():
        results.append(
            {
                "description": row["description"],
                "avg_amount": round(float(row["avg_amount"]), 2),
                "months": int(row["months"]),
                "occurrences": int(row["occurrences"]),
            }
        )

    return results
