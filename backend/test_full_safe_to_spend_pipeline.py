"""
Teste oficial do pipeline Safe-to-Spend
"""

from datetime import datetime, timezone
import polars as pl

from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor
from app.cashflow import CashflowProjector, SafeToSpendCalculator


def test_full_safe_to_spend_pipeline():
    print("\n🧪 SAFE TO SPEND – PIPELINE COMPLETO\n")

    # 1️⃣ Pluggy
    pluggy = MockPluggyClient()
    item = pluggy.create_sandbox_item()
    accounts = pluggy.get_accounts(item["id"])

    account = accounts["results"][0]
    current_balance = account["balance"]

    raw = pluggy.get_transactions(account["id"])["results"]

    # 2️⃣ Validação
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=raw,
        institution_id="pluggy_sandbox",
        item_id=item["id"],
        fetched_at=datetime.now(timezone.utc),
    )

    assert batch.total_valid > 0

    # 3️⃣ ETL
    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(batch.valid_transactions)

    assert len(clean_df) > 0

    # 4️⃣ Cashflow
    projector = CashflowProjector(horizon_days=30)
    cashflow = projector.project(
        clean_df,
        current_balance=current_balance
    )

    assert len(cashflow) == 30

    # 5️⃣ Safe to Spend
    calculator = SafeToSpendCalculator(buffer=1000.0)
    result = calculator.calculate(cashflow, days=30)

    print("📊 RESULTADO:")
    for k, v in result.items():
        print(f"{k}: {v}")

    assert result["safe_to_spend_daily"] >= 0
    assert result["safe_to_spend_total"] >= 0
    assert result["min_projected_balance"] > 0

    print("\n✅ PIPELINE VALIDADO COM SUCESSO\n")


if __name__ == "__main__":
    test_full_safe_to_spend_pipeline()
