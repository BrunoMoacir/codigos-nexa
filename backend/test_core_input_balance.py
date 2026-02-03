from app.integrations.open_finance.pluggy_mock import MockPluggyClient
import polars as pl
from datetime import datetime


def normalize_for_core(transactions: list[dict]) -> pl.DataFrame:
    """
    Adapter mínimo (temporário) para teste de contrato.
    Depois vira arquivo oficial.
    """
    rows = []

    for tx in transactions:
        rows.append({
            "transaction_id": tx["transaction_id"],
            "transaction_date": datetime.fromisoformat(
                tx["transaction_date"].replace("Z", "+00:00")
            ),
            "description": tx["description"].lower(),
            "amount": float(tx["amount"]),
            "balance": float(tx["balance"]),
        })

    return pl.DataFrame(rows).sort("transaction_date")


def test_balance_is_present():
    pluggy = MockPluggyClient()

    item = pluggy.create_sandbox_item()
    account_id = pluggy.get_accounts(item["id"])["results"][0]["id"]

    raw_transactions = pluggy.get_transactions(account_id)["results"]

    df = normalize_for_core(raw_transactions)

    print("\n📊 DATAFRAME DO CORE:")
    print(df)

    print("\n📊 SCHEMA:")
    print(df.schema)

    assert "balance" in df.columns
    assert df.select(pl.col("balance").is_null().any()).item() is False

    print("\n✅ Balance presente e consistente no Core Engine")


if __name__ == "__main__":
    test_balance_is_present()
