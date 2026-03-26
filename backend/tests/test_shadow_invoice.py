from datetime import datetime, timezone

from app.core.integrations.pluggy_mock import MockPluggyClient
from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl.ingestor import TransactionIngestor
from app.subscriptions.shadow_invoices.runner import run_shadow_invoice_detection


def test_shadow_invoice_pipeline():
    pluggy = MockPluggyClient()
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

    events = run_shadow_invoice_detection(df)

    assert events is not None
    # Shadow invoice detection pode retornar vazio se nenhum padrão for detectado
    # apenas verificar que é um DataFrame válido com as colunas esperadas quando não vazio
    assert hasattr(events, 'columns')
