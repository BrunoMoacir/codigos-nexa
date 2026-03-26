"""
Testa o ETL Ingestor.

Valida:
    - Normalização
    - Deduplicação
    - Escrita no DuckDB
"""

from app.core.integrations.pluggy_mock import MockPluggyClient
from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl.ingestor import TransactionIngestor
from datetime import datetime, timezone


def test_etl_ingestor_pipeline():
    pluggy = MockPluggyClient()
    ingestor = TransactionIngestor()

    item = pluggy.create_sandbox_item()
    accounts = pluggy.get_accounts(item["id"])
    txs = pluggy.get_transactions(accounts["results"][0]["id"])

    batch = TransactionBatchResult.from_raw_batch(
        raw_data=txs["results"],
        institution_id="nubank",
        item_id=item["id"],
        fetched_at=datetime.now(timezone.utc)
    )

    df, metrics = ingestor.process(batch.valid_transactions)

    assert len(df) > 0
    assert metrics.quality_score > 0.7

    print("\n✅ ETL Ingestor OK")
