from datetime import datetime, timezone

from app.core.integrations.pluggy_mock import MockPluggyClient
from app.forecast.etl.classifier import TransactionClassifier
from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl.ingestor import TransactionIngestor


def test_transaction_classifier_pipeline():
    pluggy = MockPluggyClient()
    classifier = TransactionClassifier(mode="RULES")
    ingestor = TransactionIngestor()

    item = pluggy.create_sandbox_item()
    acc = pluggy.get_accounts(item["id"])
    txs = pluggy.get_transactions(acc["results"][0]["id"])

    batch = TransactionBatchResult.from_raw_batch(
        raw_data=txs["results"],
        institution_id="nubank",
        item_id=item["id"],
        fetched_at=datetime.now(timezone.utc)
    )

    df, _ = ingestor.process(batch.valid_transactions)

    result = classifier.predict(df)

    assert not result.is_empty()
    assert "predicted_category" in result.columns
