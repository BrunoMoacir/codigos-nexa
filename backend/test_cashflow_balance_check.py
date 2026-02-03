import polars as pl

from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.adapters.pluggy_adapter import normalize_pluggy_transactions


def test_balance_column_exists():
    client = MockPluggyClient()

    item = client.create_sandbox_item()
    accounts = client.get_accounts(item["id"])
    account_id = accounts["results"][0]["id"]

    raw_tx = client.get_transactions(account_id)["results"]

    df = normalize_pluggy_transactions(raw_tx)

    print("\n📊 SCHEMA DO DATAFRAME NORMALIZADO:")
    print(df.schema)

    assert "balance" in df.columns, "❌ Coluna 'balance' NÃO existe no transactions_df"

    print("\n✅ Coluna 'balance' encontrada com sucesso!")


if __name__ == "__main__":
    test_balance_column_exists()
