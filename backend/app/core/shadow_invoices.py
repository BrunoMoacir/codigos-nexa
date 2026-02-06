#backend/app/core/shadow_invoices.py
import polars as pl
from datetime import date

def detect_installments(df: pl.DataFrame) -> pl.DataFrame:
    """
    Detecta padrões de parcelas (ex: 3x, 6x, 12x).
    """

    patterns = ["x", "parcela", "parcelado"]

    return df.with_columns(
        pl.col("description")
        .str.to_lowercase()
        .str.contains_any(patterns)
        .alias("is_installment")
    )


def generate_future_installments(df: pl.DataFrame, months_forward: int = 12) -> pl.DataFrame:
    """
    Projeta parcelas futuras detectadas.
    """

    installments = df.filter(pl.col("is_installment") == True)

    future_rows = []

    for row in installments.iter_rows(named=True):
        for i in range(1, months_forward + 1):
            future_rows.append({
                "date": row["date"].add_months(i),
                "amount": row["amount"],
                "description": f"{row['description']} (shadow)",
                "is_shadow": True
            })

    if not future_rows:
        return pl.DataFrame()

    return pl.DataFrame(future_rows)
