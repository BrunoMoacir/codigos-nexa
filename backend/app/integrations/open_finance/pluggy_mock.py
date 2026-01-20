class MockPluggyClient:
    """
    Simula respostas da Pluggy para desenvolvimento local
    """

    def authenticate(self):
        return "mock_access_token"

    def create_sandbox_item(self):
        return {
            "id": "mock_item_id_123",
            "status": "UPDATED",
            "connector": {
                "id": "pluggy_sandbox",
                "name": "Pluggy Sandbox Bank"
            }
        }

    def get_accounts(self, item_id: str):
        return {
            "results": [
                {
                    "id": "acc_001",
                    "type": "CHECKING",
                    "balance": 2350.75,
                    "currencyCode": "BRL",
                    "name": "Conta Corrente Mock",
                }
            ]
        }

    def get_transactions(self, account_id: str):
        return {
            "results": [
                {
                    "id": "trx_001",
                    "description": "PIX RECEBIDO",
                    "amount": 1500.00,
                    "date": "2026-01-10",
                    "type": "CREDIT",
                    "category": "TRANSFER"
                },
                {
                    "id": "trx_002",
                    "description": "SUPERMERCADO",
                    "amount": -230.50,
                    "date": "2026-01-12",
                    "type": "DEBIT",
                    "category": "FOOD"
                }
            ]
        }
