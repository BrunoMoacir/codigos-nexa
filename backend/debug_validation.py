#!/usr/bin/env python
"""Debug script to diagnose mock data validation issues"""

from datetime import datetime, timezone
from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.schemas.transaction import TransactionBatchResult

# Get mock data
client = MockPluggyClient()
item = client.create_sandbox_item()
accounts = client.get_accounts(item["id"])
account_id = accounts["results"][0]["id"]
raw_txns = client.get_transactions(account_id)

print(f"Raw transactions count: {len(raw_txns['results'])}")
print(f"\nFirst transaction:\n{raw_txns['results'][0]}\n")

# Try to validate
try:
    batch_result = TransactionBatchResult.from_raw_batch(
        raw_data=raw_txns["results"],
        institution_id="nubank",
        item_id=item["id"],
        fetched_at=datetime.now(timezone.utc)
    )
    
    print(f"✅ Valid: {len(batch_result.valid_transactions)}")
    print(f"❌ Rejected: {len(batch_result.rejected_transactions)}")
    print(f"\nBatch result fields:")
    print(f"  total_received: {batch_result.total_received}")
    print(f"  total_valid: {batch_result.total_valid}")
    print(f"  total_rejected: {batch_result.total_rejected}")
    print(f"  rejection_rate: {batch_result.rejection_rate}")
    
    if batch_result.rejected_transactions:
        print(f"\nFirst rejection reason:")
        first = batch_result.rejected_transactions[0]
        print(f"  Error Type: {first.error_type}")
        print(f"  Error Message: {first.error_message}")
        print(f"  Field Errors: {first.field_errors}")
        
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()
