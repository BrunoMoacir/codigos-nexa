"""
app/integrations/open_finance/pluggy_mock.py - Mock CORRIGIDO da Pluggy

MUDANÇAS:
    ✅ "id" → "transaction_id"
    ✅ "date" → "transaction_date"
    ✅ Adicionado "account_id" (obrigatório)
    ✅ Formato de data corrigido (ISO 8601 com timezone)
    ✅ Netflix recorrente (3 meses) para teste de assinatura
"""

from datetime import datetime, timezone


class MockPluggyClient:
    """
    Cliente mock da Pluggy para testes.
    
    Simula respostas da API Pluggy com FORMATO CORRETO para TransactionWebhook.
    """
    
    def create_sandbox_item(self) -> dict:
        return {
            "id": "mock_item_id_123",
            "connector": {
                "id": "201",  # Nubank
                "name": "Nubank"
            },
            "status": "ACTIVE"
        }
    
    def get_accounts(self, item_id: str) -> dict:
        return {
            "results": [
                {
                    "id": "acc_001",
                    "name": "Conta Corrente Mock",
                    "type": "CHECKING",
                    "balance": 5000.00,
                    "currencyCode": "BRL"
                }
            ]
        }
    
    def get_transactions(self, account_id: str) -> dict:
        return {
            "results": [
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 1: PIX Recebido (CRÉDITO)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_001",
                    "account_id": account_id,
                    "transaction_date": "2026-01-10T08:30:00Z",
                    "description": "PIX RECEBIDO",
                    "amount": 1500.00,
                    "balance": 6500.00,
                    "type": "CREDIT",
                    "category": "TRANSFER",
                    "status": "POSTED"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 2: Compra Uber (DÉBITO)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_002",
                    "account_id": account_id,
                    "transaction_date": "2026-01-15T18:45:00Z",
                    "description": "UBER *TRIP - SAO PAULO",
                    "amount": -45.50,
                    "balance": 6454.50,
                    "type": "DEBIT",
                    "category": "TRANSPORT",
                    "status": "POSTED",
                    "merchant": "Uber"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 3: Netflix (DÉBITO) - JANEIRO
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_003",
                    "account_id": account_id,
                    "transaction_date": "2026-01-20T10:00:00Z",
                    "description": "NETFLIX.COM",
                    "amount": -49.90,
                    "balance": 6404.60,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Netflix"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 4: Supermercado (DÉBITO)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_004",
                    "account_id": account_id,
                    "transaction_date": "2026-01-22T14:30:00Z",
                    "description": "CARREFOUR SAO PAULO",
                    "amount": -285.40,
                    "balance": 6119.20,
                    "type": "DEBIT",
                    "category": "GROCERIES",
                    "status": "POSTED",
                    "merchant": "Carrefour"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 5: Salário (CRÉDITO)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_005",
                    "account_id": account_id,
                    "transaction_date": "2026-01-25T06:00:00Z",
                    "description": "SALARIO - EMPRESA XYZ LTDA",
                    "amount": 8500.00,
                    "balance": 14619.20,
                    "type": "CREDIT",
                    "category": "SALARY",
                    "status": "POSTED"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 6: Duplicata intencional (para testar dedup)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_002_duplicate",
                    "account_id": account_id,
                    "transaction_date": "2026-01-15T18:45:00Z",
                    "description": "UBER *TRIP - RIO DE JANEIRO",
                    "amount": -45.50,
                    "balance": 6454.50,
                    "type": "DEBIT",
                    "category": "TRANSPORT",
                    "status": "POSTED",
                    "merchant": "Uber"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 7: Netflix (DÉBITO) - FEVEREIRO
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_006",
                    "account_id": account_id,
                    "transaction_date": "2026-02-20T10:00:00Z",
                    "description": "NETFLIX.COM",
                    "amount": -49.90,
                    "balance": 14569.30,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Netflix"
                },
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 8: Netflix (DÉBITO) - MARÇO
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    "transaction_id": "trx_007",
                    "account_id": account_id,
                    "transaction_date": "2026-03-20T10:00:00Z",
                    "description": "NETFLIX.COM",
                    "amount": -49.90,
                    "balance": 14519.40,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Netflix"
                }
            ]
        }
