"""
🧪 TESTE INTEGRADO COMPLETO - NEXA AI (VERSÃO CORRIGIDA)
═══════════════════════════════════════════════════════════════════════

Este script ajusta o PYTHONPATH automaticamente e testa TUDO.

Como executar:
    # Opção 1: Direto (ajusta PYTHONPATH automaticamente)
    python test_nexa_fixed.py
    
    # Opção 2: Com PYTHONPATH manual (do diretório raiz do projeto)
    cd /Users/gabriel-abel/projetoNexa/codigos-nexa-13
    PYTHONPATH=/Users/gabriel-abel/projetoNexa/codigos-nexa-13/backend python backend/app/etl/test_nexa_fixed.py
"""

import sys
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIX PYTHONPATH AUTOMATICAMENTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Detecta o diretório raiz do projeto
# Este arquivo está em: backend/app/etl/test_nexa_fixed.py
# Precisamos adicionar: backend/ ao PYTHONPATH

current_file = Path(__file__).resolve()
print(f"📂 Arquivo atual: {current_file}")

# Subir 2 níveis: etl/ → app/ → backend/
backend_dir = current_file.parent.parent.parent
print(f"📂 Backend dir: {backend_dir}")

# Adicionar ao PYTHONPATH
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    print(f"✅ PYTHONPATH ajustado: {backend_dir}")

# Verificar se app/ é importável
try:
    import app
    print(f"✅ Módulo 'app' encontrado em: {app.__file__}")
except ModuleNotFoundError as e:
    print(f"\n❌ ERRO: Módulo 'app' ainda não encontrado!")
    print(f"\nPossiveis soluções:")
    print(f"1. Certifique-se que existe: {backend_dir}/app/__init__.py")
    print(f"2. Execute do diretório correto:")
    print(f"   cd {backend_dir.parent}")
    print(f"   python backend/app/etl/test_nexa_fixed.py")
    print(f"\n3. Ou defina PYTHONPATH manualmente:")
    print(f"   export PYTHONPATH={backend_dir}")
    print(f"   python {current_file}")
    sys.exit(1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS (AGORA DEVEM FUNCIONAR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.transaction import (
    TransactionWebhook,
    TransactionBatchResult,
    RejectedTransaction
)
from app.etl.bank_strategy import get_bank_strategy
from app.etl import TransactionIngestor, TransactionClassifier


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DADOS DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WEBHOOK_NUBANK = {
    "id": "txn_nubank_001",
    "accountId": "acc_nubank_123",
    "date": "2024-01-15T10:30:00Z",
    "description": "COMPRA NO DÉBITO - UBER *TRIP ABC123",
    "amount": -50.75,
    "balance": 1949.25,
    "status": "POSTED",
    "type": "DEBIT",
    "category": "Transporte",
}

WEBHOOK_ITAU = {
    "id": "txn_itau_001",
    "conta": "acc_itau_456",
    "data": "15/01/2024 10:30:00",
    "descricao": "NETFLIX.COM ASSINATURA",
    "valor": "45,90",
    "saldo": "2.345,67",
    "status": "PROCESSADA",
    "tipo": "DEBITO",
}

WEBHOOK_INTER = {
    "id": "txn_inter_001",
    "account_id": "acc_inter_789",
    "date": "2024-01-15 10:30:00",
    "description": "IFOOD *PEDIDO",
    "value": "-35.50",
    "balance": "1,850.00",
    "status": "POSTED",
    "type": "DEBIT",
}

WEBHOOK_INVALID = {
    "id": "txn_invalid_001",
    "date": "2024-01-15T10:30:00Z",
    "description": "Transação inválida (sem amount)",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_section(title: str):
    print("\n" + "=" * 80)
    print(f"🧪 {title}")
    print("=" * 80)


def print_subsection(title: str):
    print(f"\n▶ {title}")
    print("-" * 80)


def test_bank_strategies():
    """TESTE 1: BankStrategy"""
    print_section("TESTE 1: BANK STRATEGIES")
    
    strategies = {
        "nubank": "TIER_1 - Excelente",
        "itau": "TIER_3 - Problemático",
        "inter": "TIER_2 - Bom",
        "unknown": "Fallback",
    }
    
    for bank_id, desc in strategies.items():
        print_subsection(f"{bank_id.upper()} ({desc})")
        strategy = get_bank_strategy(bank_id)
        print(f"✅ Strategy: {strategy.__class__.__name__}")
        print(f"   Tier: {strategy.tier.value}")
        print(f"   Bank ID: {strategy.bank_id}")


def test_pydantic_validation():
    """TESTE 2: Pydantic Validation"""
    print_section("TESTE 2: PYDANTIC VALIDATION")
    
    # Enriquecer Nubank
    print_subsection("2.1 Validação bem-sucedida (Nubank)")
    enriched_nubank = {
        **WEBHOOK_NUBANK,
        "institution_id": "nubank",
        "item_id": "item_nubank_123",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_NUBANK["id"],
        "account_id": WEBHOOK_NUBANK["accountId"],
        "transaction_date": WEBHOOK_NUBANK["date"],
    }
    
    txn = TransactionWebhook(**enriched_nubank)
    print(f"✅ Transação validada!")
    print(f"   ID: {txn.transaction_id}")
    print(f"   Amount: {txn.amount}")
    print(f"   Description: {txn.description}")
    print(f"   Status: {txn.status.value}")
    print(f"   Dedup Hash: {txn.dedup_hash[:16]}...")
    
    # Batch tolerante
    print_subsection("2.2 Batch tolerante (2 válidas + 1 inválida)")
    raw_batch = [WEBHOOK_NUBANK, WEBHOOK_INTER, WEBHOOK_INVALID]
    
    result = TransactionBatchResult.from_raw_batch(
        raw_data=raw_batch,
        institution_id="test_bank",
        item_id="item_test_123",
        fetched_at=datetime.now(timezone.utc),
        batch_id="batch_test_001"
    )
    
    print(f"✅ Batch processado!")
    print(f"   Total: {result.total_received}")
    print(f"   Válidas: {result.total_valid}")
    print(f"   Rejeitadas: {result.total_rejected}")
    print(f"   Rejection Rate: {result.rejection_rate:.1%}")
    print(f"   Alert Level: {result.alert_level}")


def test_etl_ingestor():
    """TESTE 3: ETL Ingestor"""
    print_section("TESTE 3: ETL INGESTOR")
    
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
    
    enriched_inter = {
        **WEBHOOK_INTER,
        "institution_id": "inter",
        "item_id": "item_inter_789",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_INTER["id"],
        "transaction_date": WEBHOOK_INTER["date"],
        "amount": WEBHOOK_INTER["value"],
    }
    txn_inter = TransactionWebhook(**enriched_inter)
    
    transactions = [txn_nubank, txn_inter]
    
    # Processar
    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(transactions)
    
    print(f"✅ Ingestor concluído!")
    print(f"\n   📊 Métricas:")
    print(f"      Total: {metrics.total_records}")
    print(f"      Duplicates removed: {metrics.duplicates_removed}")
    print(f"      After dedup: {metrics.records_after_dedup}")
    print(f"      Quality score: {metrics.quality_score:.2%}")
    print(f"      Processing time: {metrics.processing_time_ms:.2f}ms")
    
    print(f"\n   📋 DataFrame:")
    print(f"      Shape: {clean_df.shape}")
    print(f"      Columns: {clean_df.columns}")
    
    print(f"\n   📄 Sample:")
    print(clean_df.select([
        "transaction_id",
        "description",
        "amount",
        "data_status"
    ]).head(2))


def test_classifier():
    """TESTE 4: Classifier"""
    print_section("TESTE 4: CLASSIFIER (STUB)")
    
    enriched_nubank = {
        **WEBHOOK_NUBANK,
        "institution_id": "nubank",
        "item_id": "item_nubank_123",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_NUBANK["id"],
        "account_id": WEBHOOK_NUBANK["accountId"],
        "transaction_date": WEBHOOK_NUBANK["date"],
    }
    txn = TransactionWebhook(**enriched_nubank)
    
    ingestor = TransactionIngestor()
    clean_df, _ = ingestor.process([txn])
    
    classifier = TransactionClassifier()
    categorized_df = classifier.predict(clean_df)
    
    print(f"✅ Classifier aplicado!")
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
    
    print(f"\n   ⚠️ STUB MODE: Retorna categoria padrão 'Outros'")


def test_full_integration():
    """TESTE 5: Integração completa"""
    print_section("TESTE 5: INTEGRAÇÃO COMPLETA (Itaú)")
    
    print(f"📥 Webhook recebido (Itaú - campos não-padrão):")
    print(f"   conta: {WEBHOOK_ITAU['conta']}")
    print(f"   valor: {WEBHOOK_ITAU['valor']}")
    print(f"   data: {WEBHOOK_ITAU['data']}")
    
    # Enriquecer
    enriched = {
        **WEBHOOK_ITAU,
        "institution_id": "itau",
        "item_id": "item_itau_456",
        "fetched_at": datetime.now(timezone.utc),
        "transaction_id": WEBHOOK_ITAU["id"],
        "account_id": WEBHOOK_ITAU.get("conta"),
        "transaction_date": WEBHOOK_ITAU.get("data"),
        "description": WEBHOOK_ITAU.get("descricao"),
        "amount": WEBHOOK_ITAU.get("valor"),
        "balance": WEBHOOK_ITAU.get("saldo"),
    }
    
    # Pydantic
    txn = TransactionWebhook(**enriched)
    print(f"\n✅ Pydantic validou!")
    print(f"   Amount: {txn.amount}")
    print(f"   Date: {txn.transaction_date}")
    
    # Ingestor
    ingestor = TransactionIngestor()
    clean_df, _ = ingestor.process([txn])
    print(f"\n✅ Ingestor processou!")
    print(f"   Data status: {clean_df.select('data_status')[0, 0]}")
    
    # Classifier
    classifier = TransactionClassifier()
    categorized_df = classifier.predict(clean_df)
    print(f"\n✅ Classifier aplicou!")
    
    print(f"\n🎉 FLUXO COMPLETO EXECUTADO!")
    print(f"\n📊 DataFrame final:")
    print(categorized_df.select([
        "transaction_id",
        "description",
        "amount",
        "data_status",
        "predicted_category"
    ]))


def run_all_tests():
    """Executa todos os testes"""
    print("\n" + "🚀" * 40)
    print("🧪 NEXA AI - TESTE INTEGRADO COMPLETO")
    print("🚀" * 40)
    
    try:
        test_bank_strategies()
        test_pydantic_validation()
        test_etl_ingestor()
        test_classifier()
        test_full_integration()
        
        print("\n" + "=" * 80)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 80)
        print("\n📋 RESUMO:")
        print("   ✅ BankStrategy: OK")
        print("   ✅ Pydantic: OK")
        print("   ✅ Ingestor: OK")
        print("   ✅ Classifier: OK (stub)")
        print("   ✅ Integração: OK")
        
        print("\n🎯 PRÓXIMOS PASSOS:")
        print("   1. API Layer (FastAPI)")
        print("   2. Database Layer (SQLAlchemy)")
        print("   3. Treinar CatBoost")
        print("   4. RecurringDetector")
        print("   5. DataQualityValidator")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERRO!")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()