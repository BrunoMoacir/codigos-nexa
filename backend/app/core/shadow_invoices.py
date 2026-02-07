import pandas as pd
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

    df = pd.DataFrame(transactions)

    if df.empty:
        return []

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")

    df = df[df["amount"] < 0]
    df["abs_amount"] = df["amount"].abs()
    df = df[df["abs_amount"] <= 100]

    df["merchant"] = df["description"].apply(normalize_merchant)

    grouped = (
        df.groupby(["merchant"])
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
                "description": row["merchant"],
                "avg_amount": round(float(row["avg_amount"]), 2),
                "months": int(row["months"]),
                "occurrences": int(row["occurrences"]),
            }
        )

    return results
