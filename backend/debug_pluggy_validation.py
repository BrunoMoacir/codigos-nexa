"""
debug_pluggy_validation.py - Descobre por que transações da Pluggy são rejeitadas

Execute:
    python debug_pluggy_validation.py
"""

from datetime import datetime, timezone
from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.schemas.transaction import TransactionWebhook, TransactionBatchResult

print("="*70)
print("🔍 DEBUG: Por que transações da Pluggy são rejeitadas?")
print("="*70)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUSCAR DADOS DA PLUGGY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pluggy = MockPluggyClient()
item = pluggy.create_sandbox_item()
accounts = pluggy.get_accounts(item["id"])
account_id = accounts["results"][0]["id"]
transactions_response = pluggy.get_transactions(account_id)
raw_transactions = transactions_response.get("results", [])

print(f"\n✅ {len(raw_transactions)} transações encontradas")
print("\n" + "="*70)
print("📋 PRIMEIRA TRANSAÇÃO (JSON CRU DA PLUGGY)")
print("="*70)

import json
print(json.dumps(raw_transactions[0], indent=2, default=str))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TENTAR VALIDAR INDIVIDUALMENTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "="*70)
print("🧪 TENTANDO VALIDAR PRIMEIRA TRANSAÇÃO")
print("="*70)

try:
    # Enriquecer com campos obrigatórios (que não vêm da Pluggy)
    enriched = {
        **raw_transactions[0],
        "institution_id": "pluggy_sandbox",
        "item_id": item["id"],
        "fetched_at": datetime.now(timezone.utc)
    }
    
    tx = TransactionWebhook(**enriched)
    print("✅ Validação passou! Transação válida.")
    print(f"   ID: {tx.transaction_id}")
    print(f"   Amount: {tx.amount}")
    print(f"   Date: {tx.transaction_date}")
    
except Exception as e:
    print(f"❌ Validação falhou!")
    print(f"\n🔴 ERRO: {type(e).__name__}")
    print(f"📝 MENSAGEM: {str(e)}")
    
    # Se for ValidationError, mostrar detalhes
    from pydantic import ValidationError
    if isinstance(e, ValidationError):
        print("\n📋 ERROS DETALHADOS:")
        for error in e.errors():
            field = " → ".join(str(loc) for loc in error["loc"])
            msg = error["msg"]
            input_val = error.get("input")
            print(f"\n   Campo: {field}")
            print(f"   Erro:  {msg}")
            if input_val is not None:
                print(f"   Valor recebido: {input_val}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDAR BATCH COMPLETO PARA VER TODAS AS REJEIÇÕES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "="*70)
print("📊 VALIDANDO BATCH COMPLETO")
print("="*70)

batch_result = TransactionBatchResult.from_raw_batch(
    raw_data=raw_transactions,
    institution_id="pluggy_sandbox",
    item_id=item["id"],
    fetched_at=datetime.now(timezone.utc)
)

print(f"Total: {batch_result.total_received}")
print(f"Válidas: {batch_result.total_valid}")
print(f"Rejeitadas: {batch_result.total_rejected}")

if batch_result.rejected_transactions:
    print("\n📋 TOP 5 ERROS:")
    for error_type, count in list(batch_result.error_summary.items())[:5]:
        print(f"   {error_type}: {count}")
    
    print("\n📋 PRIMEIRA TRANSAÇÃO REJEITADA:")
    rejected = batch_result.rejected_transactions[0]
    print(f"   Tipo de erro: {rejected.error_type}")
    print(f"   Mensagem: {rejected.error_message}")
    print(f"\n   Erros por campo:")
    for field, errors in rejected.field_errors.items():
        print(f"      {field}: {errors}")

print("\n" + "="*70)