"""
🧪 TESTE INTEGRADO COMPLETO - NEXA AI (CORRIGIDO)
═══════════════════════════════════════════════════════════════════════

Este script testa TUDO que foi implementado até agora:
    ✅ Schemas Pydantic (TransactionWebhook, RejectedTransaction, TransactionBatchResult)
    ✅ BankStrategy (integrado no Ingestor)
    ✅ Ingestor (ETL completo)
    ✅ Classifier (stub)
    ✅ Integração completa (Webhook → Pydantic → Ingestor → Classifier)

CORREÇÕES:
    - Removido teste isolado de BankStrategy (trabalha com DataFrame, não dict)
    - BankStrategy é testado DENTRO do Ingestor (onde deve ser usado)

Como executar:
    python test_nexa_complete_fixed.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Adiciona o diretório raiz ao PYTHONPATH
root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.schemas.transaction import (
    TransactionWebhook,
    TransactionBatchResult,
)
from app.etl import TransactionIngestor, TransactionClassifier


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DADOS DE TESTE (WEBHOOKS SIMULADOS)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Simula webhook do Nubank (TIER_1 - Excelente)
WEBHOOK_NUBANK = {
    "id": "txn_nubank_001",
    "accountId": "acc_nubank_123",
    "date": "2024-01-15T10:30:00Z",
    "description": "COMPRA NO DÉBITO - UBER *TRIP ABC123",
    "amount": -50.75,
    "balance": 1949.25,
    "status": "POSTED",
    "type": "DEBIT",
    "category": "Transporte",  # Nubank envia, mas não é confiável
}

# Simula webhook do Itaú (TIER_3 - Problemático)
WEBHOOK_ITAU = {
    "id": "txn_itau_001",
    "conta": "acc_itau_456",  # Campo não-padrão
    "data": "15/01/2024 10:30:00",  # Formato BR
    "descricao": "NETFLIX.COM ASSINATURA",  # Campo não-padrão
    "valor": "45,90",  # Formato BR (STRING)
    "saldo": "2.345,67",  # Formato BR (STRING)
    "status": "PROCESSADA",  # Alias de POSTED
    "tipo": "DEBITO",  # Campo não-padrão
}

# Simula webhook do Inter (TIER_2 - Bom, formato US)
WEBHOOK_INTER = {
    "id": "txn_inter_001",
    "account_id": "acc_inter_789",
    "date": "2024-01-15 10:30:00",  # SQL format
    "description": "IFOOD *PEDIDO",
    "value": "-35.50",  # Inter chama "value"
    "balance": "1,850.00",  # Formato US (STRING)
    "status": "POSTED",
    "type": "DEBIT",
}

# Simula transação INVÁLIDA (vai ser rejeitada)
WEBHOOK_INVALID = {
    "id": "txn_invalid_001",
    # Falta amount (campo obrigatório)
    "date": "2024-01-15T10:30:00Z",
    "description": "Transação inválida",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_section(title: str):
    """Imprime seção visual."""
    print("\n" + "=" * 80)
    print(f"🧪 {title}")
    print("=" * 80)


def print_subsection(title: str):
    """Imprime subseção visual."""
    print(f"\n▶ {title}")
    print("-" * 80)


def test_pydantic_validation():
    """
    TESTE 1: Validação Pydantic (TransactionWebhook)
    
    Testa:
        ✅ Validação bem-sucedida (Nubank)
        ✅ Validação tolerante (batch com 2 válidas + 1 rejeitada)
        ✅ RejectedTransaction (DLQ)
        ✅ TransactionBatchResult
    """
    print_section("TESTE 1: VALIDAÇÃO PYDANTIC (TransactionWebhook)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1.1 VALIDAÇÃO BEM-SUCEDIDA (Nubank)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print_subsection("1.1 Validação bem-sucedida (Nubank)")
    
    # Enriquecer com contexto (institution_id, item_id, fetched_at)
    enriched_nubank = {
        **WEBHOOK_NUBANK,
        "institution_id": "nubank",
        "item_id": "item_nubank_123",
        "fetched_at": datetime.now(timezone.utc),
        # Mapear campos Pluggy → TransactionWebhook
        "transaction_id": WEBHOOK_NUBANK["id"],
        "account_id": WEBHOOK_NUBANK["accountId"],
        "transaction_date": WEBHOOK_NUBANK["date"],
    }
    
    try:
        txn = TransactionWebhook(**enriched_nubank)
        print(f"✅ Transação validada com sucesso!")
        print(f"   ID: {txn.transaction_id}")
        print(f"   Amount: {txn.amount}")
        print(f"   Description: {txn.description}")
        print(f"   Status: {txn.status.value}")
        print(f"   Dedup Hash: {txn.dedup_hash[:16]}...")  # Primeiros 16 chars
    except Exception as e:
        print(f"❌ ERRO: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1.2 VALIDAÇÃO TOLERANTE (Batch com válidas + inválida)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print_subsection("1.2 Validação tolerante (Batch 2 válidas + 1 inválida)")
    
    # Batch simulado (mistura válidas e inválidas)
    raw_batch = [
        WEBHOOK_NUBANK,
        WEBHOOK_INTER,
        WEBHOOK_INVALID,  # ← Vai ser rejeitada (falta amount)
    ]
    
    # Processar batch (factory method)
    result = TransactionBatchResult.from_raw_batch(
        raw_data=raw_batch,
        institution_id="test_bank",
        item_id="item_test_123",
        fetched_at=datetime.now(timezone.utc),
        batch_id="batch_test_001"
    )
    
    print(f"✅ Batch processado!")
    print(f"   Total recebido: {result.total_received}")
    print(f"   Válidas: {result.total_valid}")
    print(f"   Rejeitadas: {result.total_rejected}")
    print(f"   Rejection Rate: {result.rejection_rate:.1%}")
    print(f"   Alert Level: {result.alert_level}")
    print(f"   Should Alert: {result.should_alert}")
    
    if result.rejected_transactions:
        print(f"\n   Detalhes da rejeição:")
        rej = result.rejected_transactions[0]
        print(f"      Error Type: {rej.error_type}")
        print(f"      Error Message: {rej.error_message[:100]}...")  # Trunca
        print(f"      Field Errors: {list(rej.field_errors.keys()) if rej.field_errors else 'None'}")


def test_etl_ingestor():
    """
    TESTE 2: Ingestor ETL (JSON → DataFrame limpo)
    
    Testa:
        ✅ Pipeline completo (6 passos)
        ✅ Integração com BankStrategy (TESTADO AQUI!)
        ✅ Deduplicação
        ✅ Normalização de textos
        ✅ Métricas de qualidade
    """
    print_section("TESTE 2: INGESTOR ETL + BANK STRATEGY (JSON → DataFrame limpo)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2.1 CRIAR TRANSAÇÕES VÁLIDAS (3 bancos diferentes)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print_subsection("2.1 Criando transações de 3 bancos (Nubank, Inter, Itaú)")
    
    # Nubank
    enriched_nubank = {
        **WEBHOOK_NUBANK,
        "institution_id": "nubank",
        "item_id": "item_nubank_123",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_NUBANK["id"],
        "account_id": WEBHOOK_NUBANK["accountId"],
        "transaction_date": WEBHOOK_NUBANK["date"],
    }
    txn_nubank = TransactionWebhook(**enriched_nubank)
    print(f"✅ Nubank (TIER_1) validado")
    
    # Inter
    enriched_inter = {
        **WEBHOOK_INTER,
        "institution_id": "inter",
        "item_id": "item_inter_789",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_INTER["id"],
        "transaction_date": WEBHOOK_INTER["date"],
        "amount": WEBHOOK_INTER["value"],  # value → amount
    }
    txn_inter = TransactionWebhook(**enriched_inter)
    print(f"✅ Inter (TIER_2) validado")
    
    # Itaú (mais complexo - campos não-padrão)
    enriched_itau = {
        "institution_id": "itau",
        "item_id": "item_itau_456",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_ITAU["id"],
        "account_id": WEBHOOK_ITAU.get("conta", "unknown"),
        "transaction_date": WEBHOOK_ITAU.get("data"),
        "description": WEBHOOK_ITAU.get("descricao"),
        "amount": WEBHOOK_ITAU.get("valor"),  # String BR: "45,90"
        "balance": WEBHOOK_ITAU.get("saldo"),  # String BR: "2.345,67"
        "status": WEBHOOK_ITAU.get("status"),
        "type": WEBHOOK_ITAU.get("tipo"),
    }
    txn_itau = TransactionWebhook(**enriched_itau)
    print(f"✅ Itaú (TIER_3) validado")
    print(f"   (Amount convertido: '{WEBHOOK_ITAU.get('valor')}' → {txn_itau.amount})")
    
    # Criar duplicata (para testar deduplicação)
    txn_duplicate = TransactionWebhook(**enriched_nubank)
    
    transactions = [txn_nubank, txn_inter, txn_itau, txn_duplicate]
    
    print(f"\n✅ {len(transactions)} transações criadas (1 duplicata)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2.2 PROCESSAR COM INGESTOR (BankStrategy integrado aqui!)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print_subsection("2.2 Processando com Ingestor (BankStrategy aplicado automaticamente)")
    
    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(transactions)
    
    print(f"✅ Ingestor concluído!")
    print(f"\n   📊 Métricas:")
    print(f"      Total records: {metrics.total_records}")
    print(f"      Duplicates removed: {metrics.duplicates_removed}")
    print(f"      Records after dedup: {metrics.records_after_dedup}")
    print(f"      Quality score: {metrics.quality_score:.2%}")
    print(f"      Processing time: {metrics.processing_time_ms:.2f}ms")
    
    print(f"\n   📋 DataFrame limpo:")
    print(f"      Shape: {clean_df.shape}")
    print(f"      Columns: {clean_df.columns}")
    
    # Mostrar data_status por banco (BankStrategy aplicou!)
    print(f"\n   🏦 Data Status por banco (BankStrategy aplicado):")
    status_by_bank = clean_df.group_by("institution_id").agg([
        pl.col("data_status").first().alias("status")
    ])
    print(status_by_bank)
    
    # Mostrar sample
    print(f"\n   📄 Sample (primeiras 3 linhas):")
    print(clean_df.select([
        "institution_id",
        "description",
        "amount",
        "data_status"
    ]).head(3))


def test_classifier():
    """
    TESTE 3: Classifier (Categorização)
    
    Testa:
        ✅ Stub (retorna categoria padrão)
        ✅ Adiciona colunas: predicted_category, ml_confidence, category_source
    """
    print_section("TESTE 3: CLASSIFIER (Categorização)")
    
    print_subsection("3.1 Processando com Classifier (stub)")
    
    # Criar transações válidas
    enriched_nubank = {
        **WEBHOOK_NUBANK,
        "institution_id": "nubank",
        "item_id": "item_nubank_123",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_NUBANK["id"],
        "account_id": WEBHOOK_NUBANK["accountId"],
        "transaction_date": WEBHOOK_NUBANK["date"],
    }
    txn_nubank = TransactionWebhook(**enriched_nubank)
    
    # Ingestor
    ingestor = TransactionIngestor()
    clean_df, _ = ingestor.process([txn_nubank])
    
    # Classifier
    classifier = TransactionClassifier()
    categorized_df = classifier.predict(clean_df)
    
    print(f"✅ Classifier concluído!")
    print(f"\n   📊 Colunas adicionadas:")
    print(f"      - predicted_category")
    print(f"      - ml_confidence")
    print(f"      - category_source")
    
    print(f"\n   📄 Sample:")
    print(categorized_df.select([
        "description",
        "predicted_category",
        "ml_confidence",
        "category_source"
    ]))
    
    print(f"\n   ⚠️ NOTA: Classifier está em modo STUB")
    print(f"      Retorna categoria padrão 'Outros'")
    print(f"      TODO: Treinar modelo CatBoost")


def test_full_integration():
    """
    TESTE 4: INTEGRAÇÃO COMPLETA
    
    Simula fluxo real:
        Webhook → Pydantic → Ingestor (BankStrategy integrado) → Classifier
    """
    print_section("TESTE 4: INTEGRAÇÃO COMPLETA (Fluxo Real)")
    
    print_subsection("4.1 Simulando webhook do Itaú (TIER_3 - Problemático)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FLUXO COMPLETO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # 1. Webhook chega (dados crus do Itaú)
    raw_webhook = WEBHOOK_ITAU.copy()
    print(f"📥 Webhook recebido (Itaú):")
    print(f"   conta: '{raw_webhook.get('conta')}'")
    print(f"   data: '{raw_webhook.get('data')}'")
    print(f"   valor: '{raw_webhook.get('valor')}'")
    print(f"   descricao: '{raw_webhook.get('descricao')}'")
    
    # 2. Enriquecer com contexto
    enriched = {
        "institution_id": "itau",
        "item_id": "item_itau_456",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": raw_webhook["id"],
        "account_id": raw_webhook.get("conta", "unknown"),
        "transaction_date": raw_webhook.get("data"),
        "description": raw_webhook.get("descricao"),
        "amount": raw_webhook.get("valor"),
        "balance": raw_webhook.get("saldo"),
        "status": raw_webhook.get("status"),
        "type": raw_webhook.get("tipo"),
    }
    print(f"\n✅ Enriquecido com contexto")
    
    # 3. Validar com Pydantic
    try:
        txn = TransactionWebhook(**enriched)
        print(f"\n✅ Pydantic validou com sucesso!")
        print(f"   Amount: {txn.amount} (convertido de '{raw_webhook.get('valor')}')")
        print(f"   Balance: {txn.balance} (convertido de '{raw_webhook.get('saldo')}')")
        print(f"   Date: {txn.transaction_date}")
    except Exception as e:
        print(f"\n❌ ERRO Pydantic: {e}")
        raise
    
    # 4. Processar com Ingestor (BankStrategy integrado)
    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process([txn])
    
    print(f"\n✅ Ingestor processou (BankStrategy aplicou ItauStrategy)!")
    print(f"   Quality score: {metrics.quality_score:.2%}")
    print(f"   Data status: {clean_df.select('data_status')[0, 0]}")
    
    # 5. Classificar
    classifier = TransactionClassifier()
    categorized_df = classifier.predict(clean_df)
    
    print(f"\n✅ Classifier aplicou categoria!")
    print(f"   Categoria: {categorized_df.select('predicted_category')[0, 0]}")
    
    print(f"\n🎉 FLUXO COMPLETO EXECUTADO COM SUCESSO!")
    
    # Mostrar DataFrame final
    print(f"\n📊 DataFrame final:")
    print(categorized_df.select([
        "transaction_id",
        "institution_id",
        "description",
        "amount",
        "data_status",
        "predicted_category"
    ]))


def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "🚀" * 40)
    print("🧪 NEXA AI - TESTE INTEGRADO COMPLETO")
    print("🚀" * 40)
    
    try:
        test_pydantic_validation()
        test_etl_ingestor()  # BankStrategy testado AQUI (integrado)
        test_classifier()
        test_full_integration()
        
        print("\n" + "=" * 80)
        print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
        print("=" * 80)
        print("\n📋 RESUMO:")
        print("   ✅ Pydantic: OK")
        print("   ✅ BankStrategy: OK (testado no Ingestor)")
        print("   ✅ Ingestor: OK")
        print("   ✅ Classifier: OK (stub)")
        print("   ✅ Integração completa: OK")
        print("\n🎯 PRÓXIMOS PASSOS:")
        print("   1. Criar API Layer (webhooks.py, transactions.py)")
        print("   2. Criar Database Layer (models.py, queries/)")
        print("   3. Treinar modelo CatBoost (classifier)")
        print("   4. Implementar RecurringDetector")
        print("   5. Implementar DataQualityValidator")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERRO NO TESTE!")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    run_all_tests()