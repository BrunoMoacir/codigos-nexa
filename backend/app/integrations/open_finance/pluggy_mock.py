"""
app/integrations/open_finance/pluggy_mock.py - Mock CORRIGIDO da Pluggy

MUDANÇAS:
    ✅ "id" → "transaction_id"
    ✅ "date" → "transaction_date"
    ✅ Adicionado "account_id" (obrigatório)
    ✅ Formato de data corrigido (ISO 8601 com timezone)
"""

from datetime import datetime, timezone


class MockPluggyClient:
    """
    Cliente mock da Pluggy para testes.
    
    Simula respostas da API Pluggy com FORMATO CORRETO para TransactionWebhook.
    """
    
    def create_sandbox_item(self) -> dict:
        """
        Simula criação de item sandbox.
        
        Returns:
            dict com id do item criado
        """
        return {
            "id": "mock_item_id_123",
            "connector": {
                "id": "201",  # Nubank
                "name": "Nubank"
            },
            "status": "ACTIVE"
        }
    
    def get_accounts(self, item_id: str) -> dict:
        """
        Simula busca de contas de um item.
        
        Args:
            item_id: ID do item
            
        Returns:
            dict com lista de contas
        """
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
        """
        Simula busca de transações de uma conta.
        
        ✅ CORRIGIDO: Agora retorna campos compatíveis com TransactionWebhook
        
        Args:
            account_id: ID da conta
            
        Returns:
            dict com lista de transações NO FORMATO CORRETO
        """
        return {
            "results": [
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TRANSAÇÃO 1: PIX Recebido (CRÉDITO)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                {
                    # ✅ CORRIGIDO: "id" → "transaction_id"
                    "transaction_id": "trx_001",
                    
                    # ✅ CORRIGIDO: Adicionado account_id (obrigatório)
                    "account_id": account_id,
                    
                    # ✅ CORRIGIDO: "date" → "transaction_date" com ISO 8601
                    "transaction_date": "2026-01-10T08:30:00Z",
                    
                    "description": "PIX RECEBIDO",
                    "amount": 1500.00,
                    "balance": 6500.00,  # Saldo após transação
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
                # TRANSAÇÃO 3: Netflix (DÉBITO)
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
                    "transaction_id": "trx_002_duplicate",  # ID diferente
                    "account_id": account_id,
                    "transaction_date": "2026-01-15T18:45:00Z",  # Mesma data
                    "description": "UBER *TRIP - RIO DE JANEIRO",  # Primeiros 20 chars iguais
                    "amount": -45.50,  # Mesmo amount
                    "balance": 6454.50,
                    "type": "DEBIT",
                    "category": "TRANSPORT",
                    "status": "POSTED",
                    "merchant": "Uber"
                }
            ]
        }