# test_cashflow_projector_90d.py

import polars as pl
from datetime import datetime, timezone

from app.cashflow.projector import CashflowProjector


def load_core_df():
    return pl.DataFrame({
        "transaction_id": [
            "trx_001", "trx_002", "trx_002_duplicate",
            "trx_003", "trx_004", "trx_005",
            "trx_006", "trx_007"
        ],
        "transaction_date": [
            datetime(2026, 1, 10, tzinfo=timezone.utc),
            datetime(2026, 1, 15, tzinfo=timezone.utc),
            datetime(2026, 1, 15, tzinfo=timezone.utc),
            datetime(2026, 1, 20, tzinfo=timezone.utc),
            datetime(2026, 1, 22, tzinfo=timezone.utc),
            datetime(2026, 1, 25, tzinfo=timezone.utc),
            datetime(2026, 2, 20, tzinfo=timezone.utc),
            datetime(2026, 3, 20, tzinfo=timezone.utc),
        ],
        "description": [
            "pix recebido",
            "uber",
            "uber duplicate",
            "netflix.com",
            "carrefour",
            "salario",
            "netflix.com",
            "netflix.com"
        ],
        "amount": [
            1500.0, -45.5, -45.5, -49.9,
            -285.4, 8500.0, -49.9, -49.9
        ],
        "balance": [
            6500.0, 6454.5, 6454.5, 6404.6,
            6119.2, 14619.2, 14569.3, 14519.4
        ]
    })


def load_shadow_invoices():
    return pl.DataFrame({
        "type": ["SUBSCRIPTION"],
        "amount": [-49.9],
        "next_due_date": [
            datetime(2026, 4, 19, 10, 0, tzinfo=timezone.utc)
        ],
        "confidence": [0.9]
    })


if __name__ == "__main__":
    core_df = load_core_df()
    shadow_df = load_shadow_invoices()

    projector = CashflowProjector(horizon_days=90)
    projection = projector.project(core_df, shadow_df)

    print("\n📈 CASHFLOW PROJETADO (90 DIAS)")
    print(projection.head(10))
    print("...")
    print(projection.tail(5))

    min_balance = projection["projected_balance"].min()
    break_date = projection.filter(
        pl.col("projected_balance") < 0
    ).select("date").head(1)

    print("\n🔎 ANÁLISE:")
    print(f"Saldo mínimo projetado: {min_balance:.2f}")

    if break_date.height > 0:
        print("❌ Quebra de caixa em:", break_date.item())
    else:
        print("✅ Nenhuma quebra de caixa nos próximos 90 dias")
