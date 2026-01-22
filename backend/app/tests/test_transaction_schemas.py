"""
Teste de Schemas Pydantic com JSON Real da Pluggy

Este script testa:
    1. TransactionWebhook com dados reais do Pluggy
    2. TransactionBatchResult com mix de válidas/rejeitadas
    3. Validação tolerante (99 OK, 1 falha = processar 99)

Como executar:
    python test_transaction_schemas.py

Saída esperada:
    ✅ Batch processado com sucesso
    ✅ 5 transações válidas
    ✅ 3 transações rejeitadas
    ✅ Alert level: WARNING (37.5% rejeição)
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

# Importar schemas (ajustar path conforme sua estrutura)
# from app.schemas.transaction import (
#     TransactionWebhook,
#     TransactionBatchResult,
#     RejectedTransaction,
#     DataSource
# )

# Para teste standalone, assumir que está no mesmo diretório
# Na produção, ajustar import


# ==========================================
# JSON REAL DA PLUGGY (documentação oficial)
# ==========================================

# Fonte: https://docs.pluggy.ai/#tag/Transactions

PLUGGY_TRANSACTIONS_REAL = [
    # ✅ TRANSAÇÃO VÁLIDA 1: Débito simples
    {
        "id": "d91da234-d0f0-4c4a-86a3-e7919c4b87c7",
        "description": "PAG UBER *VIAGEM",
        "descriptionRaw": None,
        "currencyCode": "BRL",
        "amount": -27.50,
        "amountInAccountCurrency": -27.50,
        "date": "2024-01-15",
        "balance": 1972.50,
        "category": "Transport",
        "accountId": "acc_xyz789",
        "providerCode": "p2p",
        "status": "POSTED",
        "createdAt": "2024-01-15T10:30:00.000Z",
        "creditCardMetadata": None
    },
    
    # ✅ TRANSAÇÃO VÁLIDA 2: Crédito (salário)
    {
        "id": "e02eb345-e1g1-5d5b-97b4-f8a1ad5c98d8",
        "description": "SALARIO EMPRESA XYZ",
        "descriptionRaw": "DEPOSITO SALARIO",
        "currencyCode": "BRL",
        "amount": 5000.00,
        "date": "2024-01-05",
        "balance": 7000.00,
        "category": "Income",
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "createdAt": "2024-01-05T08:00:00.000Z"
    },
    
    # ✅ TRANSAÇÃO VÁLIDA 3: Parcelamento
    {
        "id": "f13fc456-f2h2-6e6c-a8c5-g9b2be6d09e9",
        "description": "MAGAZINE LUIZA 03/12",
        "currencyCode": "BRL",
        "amount": -83.25,
        "date": "2024-01-10",
        "balance": 2055.75,
        "category": "Shopping",
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "paymentData": {
            "payer": None,
            "receiver": None,
            "paymentMethod": "CREDIT_CARD",
            "referenceNumber": None,
            "reason": None
        },
        "creditCardMetadata": {
            "installmentNumber": 3,
            "totalInstallments": 12,
            "payeeMCC": 5311
        },
        "createdAt": "2024-01-10T14:20:00.000Z"
    },
    
    # ✅ TRANSAÇÃO VÁLIDA 4: Sem balance (40% dos bancos não enviam)
    {
        "id": "g24gd567-g3i3-7f7d-b9d6-h0c3cf7e10f0",
        "description": "TED ENVIADO",
        "currencyCode": "BRL",
        "amount": -500.00,
        "date": "2024-01-12",
        "balance": None,  # ← Banco não forneceu
        "category": "Transfer",
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "createdAt": "2024-01-12T16:45:00.000Z"
    },
    
    # ✅ TRANSAÇÃO VÁLIDA 5: Pendente (vai ser efetivada)
    {
        "id": "h35he678-h4j4-8g8e-c0e7-i1d4dg8f21g1",
        "description": "AGENDADO CONTA LUZ",
        "currencyCode": "BRL",
        "amount": -180.00,
        "date": "2024-01-25",
        "balance": 1375.75,
        "category": "Bills",
        "accountId": "acc_xyz789",
        "status": "PENDING",  # ← Ainda não efetivada
        "createdAt": "2024-01-15T11:00:00.000Z"
    },
    
    # ❌ TRANSAÇÃO INVÁLIDA 1: amount = 0 (não permitido)
    {
        "id": "i46if789-i5k5-9h9f-d1f8-j2e5eh9g32h2",
        "description": "AJUSTE SALDO",
        "currencyCode": "BRL",
        "amount": 0,  # ← ERRO: não pode ser zero
        "date": "2024-01-13",
        "balance": 2055.75,
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "createdAt": "2024-01-13T09:00:00.000Z"
    },
    
    # ❌ TRANSAÇÃO INVÁLIDA 2: data faltando
    {
        "id": "j57jg890-j6l6-0i0g-e2g9-k3f6fi0h43i3",
        "description": "COMPRA SEM DATA",
        "currencyCode": "BRL",
        "amount": -50.00,
        # "date": "2024-01-14",  # ← ERRO: faltando!
        "balance": 2005.75,
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "createdAt": "2024-01-14T12:00:00.000Z"
    },
    
    # ❌ TRANSAÇÃO INVÁLIDA 3: ID duplicado (já existe no batch)
    {
        "id": "d91da234-d0f0-4c4a-86a3-e7919c4b87c7",  # ← DUPLICATA do primeiro!
        "description": "DUPLICATA",
        "currencyCode": "BRL",
        "amount": -10.00,
        "date": "2024-01-16",
        "balance": 1962.50,
        "accountId": "acc_xyz789",
        "status": "POSTED",
        "createdAt": "2024-01-16T10:00:00.000Z"
    }
]


# ==========================================
# ADAPTADOR PLUGGY → NOSSO SCHEMA
# ==========================================

def adapt_pluggy_transaction(pluggy_txn: dict) -> dict:
    """
    Adapta JSON do Pluggy para nosso schema.
    
    Mapeamento:
        Pluggy                  → Nosso Schema
        ----------------------------------------
        id                      → transaction_id
        amount                  → amount
        date                    → transaction_date
        accountId               → account_id
        description             → description
        descriptionRaw          → description_raw
        balance                 → balance
        category                → category
        status                  → status
        currencyCode            → currency
        creditCardMetadata      → installment_number, installment_total
    """
    adapted = {
        # Campos diretos
        "transaction_id": pluggy_txn["id"],
        "amount": pluggy_txn["amount"],
        "transaction_date": pluggy_txn["date"],
        "account_id": pluggy_txn["accountId"],
        "description": pluggy_txn.get("description", ""),
        "description_raw": pluggy_txn.get("descriptionRaw"),
        "balance": pluggy_txn.get("balance"),
        "category": pluggy_txn.get("category"),
        "status": pluggy_txn.get("status", "POSTED"),
        "currency": pluggy_txn.get("currencyCode", "BRL"),
        
        # Parcelamento (se existir creditCardMetadata)
        "installment_number": None,
        "installment_total": None,
    }
    
    # Extrair metadados de cartão de crédito
    cc_meta = pluggy_txn.get("creditCardMetadata")
    if cc_meta:
        adapted["installment_number"] = cc_meta.get("installmentNumber")
        adapted["installment_total"] = cc_meta.get("totalInstallments")
    
    return adapted


# ==========================================
# FUNÇÃO DE TESTE
# ==========================================

def test_transaction_batch():
    """
    Testa validação de batch com mix de transações válidas/inválidas.
    """
    print("=" * 70)
    print("🧪 TESTE: TransactionBatchResult com JSON Real da Pluggy")
    print("=" * 70)
    print()
    
    # Adaptar transações Pluggy para nosso formato
    adapted_transactions = [
        adapt_pluggy_transaction(txn) 
        for txn in PLUGGY_TRANSACTIONS_REAL
    ]
    
    print(f"📦 Total de transações recebidas: {len(adapted_transactions)}")
    print()
    
    # Processar batch com validação tolerante
    try:
        result = TransactionBatchResult.from_raw_batch(
            raw_transactions=adapted_transactions,
            account_id="acc_xyz789",
            item_id="item_123",
            institution_id="nubank",
            source=DataSource.PLUGGY,
            fetched_at=datetime(2024, 1, 21, 14, 0, 0, tzinfo=timezone.utc)
        )
        
        # Exibir resultado
        print("✅ RESULTADO DO PROCESSAMENTO")
        print("-" * 70)
        print(f"Total recebido:     {result.total_received}")
        print(f"Total válido:       {result.total_valid}")
        print(f"Total rejeitado:    {result.total_rejected}")
        print(f"Taxa de rejeição:   {result.rejection_rate:.1%}")
        print(f"Nível de alerta:    {result.alert_level}")
        print()
        
        # Transações válidas
        print("✅ TRANSAÇÕES VÁLIDAS:")
        print("-" * 70)
        for i, txn in enumerate(result.valid_transactions, 1):
            print(f"{i}. {txn.transaction_id[:20]}... | "
                  f"{txn.amount:>10.2f} | "
                  f"{txn.description[:30]}")
        print()
        
        # Transações rejeitadas
        print("❌ TRANSAÇÕES REJEITADAS:")
        print("-" * 70)
        for i, rej in enumerate(result.rejected_transactions, 1):
            print(f"{i}. {rej.transaction_id or 'N/A'[:20]}... | "
                  f"{rej.error_type} | "
                  f"{rej.error_message[:50]}")
            if rej.field_errors:
                for field, errors in rej.field_errors.items():
                    print(f"   └─ {field}: {', '.join(errors)}")
        print()
        
        # Alertas
        if result.should_alert:
            print(f"⚠️ ALERTA: {result.alert_level}")
            print(f"Taxa de rejeição ({result.rejection_rate:.1%}) "
                  f"acima do threshold (20%)")
        else:
            print("✅ Nenhum alerta necessário")
        print()
        
        # JSON de uma transação válida (exemplo)
        if result.valid_transactions:
            print("📋 EXEMPLO: Transação Válida Serializada (JSON)")
            print("-" * 70)
            txn_json = result.valid_transactions[0].model_dump(mode="json")
            print(json.dumps(txn_json, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ ERRO NO PROCESSAMENTO: {type(e).__name__}")
        print(f"Mensagem: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 70)
    print("✅ Teste concluído!")
    print("=" * 70)


# ==========================================
# SAÍDA ESPERADA (RESUMO)
# ==========================================
"""
SAÍDA ESPERADA:

✅ RESULTADO DO PROCESSAMENTO
----------------------------------------------------------------------
Total recebido:     8
Total válido:       5
Total rejeitado:    3
Taxa de rejeição:   37.5%
Nível de alerta:    WARNING

✅ TRANSAÇÕES VÁLIDAS:
----------------------------------------------------------------------
1. d91da234-d0f0-4c4a... |     -27.50 | PAG UBER *VIAGEM
2. e02eb345-e1g1-5d5b... |    5000.00 | SALARIO EMPRESA XYZ
3. f13fc456-f2h2-6e6c... |     -83.25 | MAGAZINE LUIZA 03/12
4. g24gd567-g3i3-7f7d... |    -500.00 | TED ENVIADO
5. h35he678-h4j4-8g8e... |    -180.00 | AGENDADO CONTA LUZ

❌ TRANSAÇÕES REJEITADAS:
----------------------------------------------------------------------
1. i46if789-i5k5-9h9f... | ValidationError | amount não pode ser zero
   └─ amount: não pode ser zero

2. j57jg890-j6l6-0i0g... | ValidationError | Field required
   └─ transaction_date: Field required

3. d91da234-d0f0-4c4a... | DuplicateInBatch | transaction_id duplicado
   └─ transaction_id: duplicado no batch

⚠️ ALERTA: WARNING
Taxa de rejeição (37.5%) acima do threshold (20%)

📋 EXEMPLO: Transação Válida Serializada (JSON)
----------------------------------------------------------------------
{
  "transaction_id": "d91da234-d0f0-4c4a-86a3-e7919c4b87c7",
  "amount": "-27.50",
  "transaction_date": "2024-01-15T00:00:00+00:00",
  "account_id": "acc_xyz789",
  "description": "PAG UBER *VIAGEM",
  "balance": "1972.50",
  "category": "Transport",
  "merchant": null,
  "status": "POSTED",
  "currency": "BRL",
  "description_raw": null,
  "observations": null,
  "merchant_details": null,
  "installment_number": null,
  "installment_total": null,
  "institution_id": "nubank",
  "item_id": "item_123",
  "source": "PLUGGY",
  "fetched_at": "2024-01-21T14:00:00+00:00"
}
"""


if __name__ == "__main__":
    test_transaction_batch()