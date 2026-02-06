"backend/app/adapters/bank_adapter.py"
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

from app.schemas.transaction import TransactionWebhook


def adapt_simulation_to_webhook(raw: list[dict]) -> list[TransactionWebhook]:
    """
    Converte dados simulados de banco → TransactionWebhook (contrato interno).

    Responsabilidade:
        - Completar campos obrigatórios do webhook
        - Garantir tipos corretos (Decimal, datetime)
        - Gerar IDs técnicos (transaction_id, item_id)
    """

    webhook_transactions: list[TransactionWebhook] = []

    now = datetime.now(timezone.utc)

    for item in raw:
        tx = TransactionWebhook(
            transaction_id=str(uuid4()),

            # ID técnico do item bancário (simulado)
            item_id=f'{item["bank"]}_item',

            # Em simulação, 1 conta por banco
            account_id=f'{item["bank"]}_account',

            institution_id=item["bank"],

            description=item["description"],

            amount=Decimal(str(item["amount"])),

            transaction_date=datetime.fromisoformat(item["date"]),

            fetched_at=now,

            dedup_hash=f'{item["bank"]}_{item["description"]}_{item["date"]}',
        )

        webhook_transactions.append(tx)

    return webhook_transactions
