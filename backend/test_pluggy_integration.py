"""
test_pluggy_integration.py - Testa integração completa Pluggy → ETL

Execute:
    python test_pluggy_integration.py
    
O que este script faz:
    1. Conecta na Pluggy (sandbox ou produção)
    2. Busca transações de uma conta
    3. Processa com ETL completo
    4. Exibe resultados
"""

import sys
import logging
import polars as pl 
from datetime import datetime, timezone

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO DE LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    from app.integrations.open_finance.pluggy_mock import MockPluggyClient
    # TODO: Quando tiver Pluggy real, descomentar:
    # from app.integrations.open_finance.pluggy import PluggyClient
    
    from app.schemas.transaction import TransactionBatchResult
    from app.etl import TransactionIngestor, TransactionClassifier
    
except ImportError as e:
    print(f"❌ Erro ao importar módulos: {e}")
    print("\n💡 SOLUÇÃO:")
    print("   1. Certifique-se de estar na pasta backend/")
    print("   2. Ative o ambiente virtual: .venv\\Scripts\\Activate")
    print("   3. Rode novamente: python test_pluggy_integration.py")
    sys.exit(1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÃO PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_pluggy_integration():
    """
    Testa integração completa:
        Pluggy → Validação → ETL → Resultado
    """
    
    print("="*70)
    print("🧪 TESTE DE INTEGRAÇÃO: PLUGGY → ETL")
    print("="*70)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1: BUSCAR DADOS DA PLUGGY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n1️⃣ Conectando na Pluggy...")
    
    try:
        # Usar mock (sandbox da Pluggy)
        pluggy = MockPluggyClient()
        
        # Criar item sandbox
        item = pluggy.create_sandbox_item()
        item_id = item["id"]
        
        print(f"✅ Item criado: {item_id}")
        
        # Buscar contas
        accounts = pluggy.get_accounts(item_id)
        
        if not accounts.get("results"):
            print("❌ Nenhuma conta encontrada")
            return
        
        account_id = accounts["results"][0]["id"]
        account_name = accounts["results"][0].get("name", "Conta")
        
        print(f"✅ Conta encontrada: {account_name} (ID: {account_id})")
        
        # Buscar transações
        print(f"\n2️⃣ Buscando transações da conta...")
        
        transactions_response = pluggy.get_transactions(account_id)
        raw_transactions = transactions_response.get("results", [])
        
        if not raw_transactions:
            print("⚠️  Nenhuma transação encontrada na conta")
            return
        
        print(f"✅ {len(raw_transactions)} transações encontradas")
        
    except Exception as e:
        print(f"❌ Erro ao buscar dados da Pluggy: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2: VALIDAR COM PYDANTIC (TransactionBatchResult)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print(f"\n3️⃣ Validando transações com Pydantic...")
    
    try:
        batch_result = TransactionBatchResult.from_raw_batch(
            raw_data=raw_transactions,
            institution_id="pluggy_sandbox",  # Sandbox
            item_id=item_id,
            fetched_at=datetime.now(timezone.utc)
        )
        
        print(f"✅ Validação concluída:")
        print(f"   Total recebido:   {batch_result.total_received}")
        print(f"   Total válido:     {batch_result.total_valid}")
        print(f"   Total rejeitado:  {batch_result.total_rejected}")
        print(f"   Rejection rate:   {batch_result.rejection_rate:.1%}")
        
        if batch_result.should_alert:
            print(f"\n⚠️  ALERTA {batch_result.alert_level}: {batch_result.alert_message}")
        
    except Exception as e:
        print(f"❌ Erro na validação: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3: PROCESSAR COM ETL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if not batch_result.valid_transactions:
        print("\n⚠️  Nenhuma transação válida para processar")
        return
    
    print(f"\n4️⃣ Processando com ETL Pipeline...")
    
    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ETL 1: INGESTOR (Limpa + Normaliza)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print("   → Ingestor: Limpando e normalizando...")
        
        ingestor = TransactionIngestor()
        clean_df, metrics = ingestor.process(batch_result.valid_transactions)
        
        print(f"   ✅ Ingestor concluído:")
        print(f"      Records processados:   {metrics.records_after_dedup}")
        print(f"      Duplicatas removidas:  {metrics.duplicates_removed}")
        print(f"      Quality score:         {metrics.quality_score:.1%}")
        print(f"      Tempo processamento:   {metrics.processing_time_ms:.2f}ms")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ETL 2: CLASSIFIER (Categoriza)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print("\n   → Classifier: Categorizando...")
        
        classifier = TransactionClassifier()
        categorized_df = classifier.predict(clean_df)
        
        print(f"   ✅ Classifier concluído")
        print(f"      Transações categorizadas: {len(categorized_df)}")
        
    except Exception as e:
        print(f"❌ Erro no ETL Pipeline: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4: EXIBIR RESULTADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "="*70)
    print("📊 RESULTADO FINAL (Primeiras 10 transações)")
    print("="*70)
    
    # Selecionar colunas importantes
    df_display = categorized_df.select([
        "transaction_id",
        "amount",
        "description",
        "predicted_category",
        "ml_confidence",
        "transaction_type",
        "month",
        "day_of_week"
    ])
    
    print(df_display.head(10))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ESTATÍSTICAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "="*70)
    print("📈 ESTATÍSTICAS")
    print("="*70)
    
    # Total por tipo (DEBIT vs CREDIT)
    total_debit = categorized_df.filter(
        categorized_df["transaction_type"] == "DEBIT"
    )["amount"].sum()
    
    total_credit = categorized_df.filter(
        categorized_df["transaction_type"] == "CREDIT"
    )["amount"].sum()
    
    print(f"Total Débitos:  R$ {abs(total_debit):,.2f}")
    print(f"Total Créditos: R$ {total_credit:,.2f}")
    print(f"Saldo líquido:  R$ {total_credit + total_debit:,.2f}")
    
    # Total por categoria
    print("\n📊 Total por categoria:")
    by_category = (
        categorized_df
        .group_by("predicted_category")
        .agg(pl.col("amount").sum().alias("total"))
        .sort("total")
    )
    
    for row in by_category.iter_rows(named=True):
        category = row["predicted_category"]
        total = row["total"]
        print(f"   {category:.<30} R$ {total:>10,.2f}")
    
    print("\n" + "="*70)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("="*70)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUTAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    test_pluggy_integration()