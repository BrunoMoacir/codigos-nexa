"""
test_etl_complete_pipeline.py - Teste End-to-End Completo

FLUXO COMPLETO:
    Pluggy API → Pydantic Validation → ETL (Ingestor + Classifier) → Shadow Invoices

Execute:
    python test_etl_complete_pipeline.py
"""

import logging
from datetime import datetime, timezone

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO DE LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor, TransactionClassifier
from app.etl.shadow_invoices.runner import run_shadow_invoice_detection


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÃO PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_complete_etl_pipeline():
    """
    Testa pipeline completo:
        Pluggy → Validation → ETL → Shadow Invoices
    """
    
    print("="*70)
    print("🧪 TESTE END-TO-END: PIPELINE COMPLETO")
    print("="*70)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 1: BUSCAR DADOS DA PLUGGY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "━"*70)
    print("1️⃣ BUSCAR DADOS DA PLUGGY (SANDBOX)")
    print("━"*70)
    
    try:
        pluggy = MockPluggyClient()
        
        # Criar item sandbox
        item = pluggy.create_sandbox_item()
        item_id = item["id"]
        print(f"✅ Item criado: {item_id}")
        
        # Buscar contas
        accounts = pluggy.get_accounts(item_id)
        account_id = accounts["results"][0]["id"]
        account_name = accounts["results"][0].get("name", "Conta")
        print(f"✅ Conta encontrada: {account_name} (ID: {account_id})")
        
        # Buscar transações
        transactions_response = pluggy.get_transactions(account_id)
        raw_transactions = transactions_response.get("results", [])
        print(f"✅ {len(raw_transactions)} transações recebidas da Pluggy")
        
    except Exception as e:
        print(f"❌ Erro ao buscar dados da Pluggy: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 2: VALIDAR COM PYDANTIC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "━"*70)
    print("2️⃣ VALIDAR COM PYDANTIC (TransactionBatchResult)")
    print("━"*70)
    
    try:
        batch_result = TransactionBatchResult.from_raw_batch(
            raw_data=raw_transactions,
            institution_id="pluggy_sandbox",
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
        
        if not batch_result.valid_transactions:
            print("\n⚠️  Nenhuma transação válida para processar")
            return
        
    except Exception as e:
        print(f"❌ Erro na validação: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 3: ETL - INGESTOR (Limpar + Normalizar)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "━"*70)
    print("3️⃣ ETL - INGESTOR (Limpar + Normalizar)")
    print("━"*70)
    
    try:
        ingestor = TransactionIngestor()
        clean_df, metrics = ingestor.process(batch_result.valid_transactions)
        
        print(f"✅ Ingestor concluído:")
        print(f"   Records processados:   {metrics.records_after_dedup}")
        print(f"   Duplicatas removidas:  {metrics.duplicates_removed}")
        print(f"   Quality score:         {metrics.quality_score:.1%}")
        print(f"   Tempo processamento:   {metrics.processing_time_ms:.2f}ms")
        
    except Exception as e:
        print(f"❌ Erro no Ingestor: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 4: ETL - CLASSIFIER (Categorizar)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "━"*70)
    print("4️⃣ ETL - CLASSIFIER (Categorizar)")
    print("━"*70)
    
    try:
        classifier = TransactionClassifier()
        categorized_df = classifier.predict(clean_df)
        
        print(f"✅ Classifier concluído:")
        print(f"   Transações categorizadas: {len(categorized_df)}")
        
    except Exception as e:
        print(f"❌ Erro no Classifier: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 5: SHADOW INVOICES (Detectar obrigações futuras)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "━"*70)
    print("5️⃣ SHADOW INVOICES (Detectar obrigações futuras)")
    print("━"*70)
    
    try:
        shadow_invoices = run_shadow_invoice_detection(categorized_df)
        
        if shadow_invoices.is_empty():
            print("⚠️  Nenhuma shadow invoice detectada")
            print("   (Normal se não houver assinaturas/parcelamentos no dataset)")
        else:
            print(f"✅ Shadow invoices detectadas: {len(shadow_invoices)}")
        
    except Exception as e:
        print(f"❌ Erro na detecção de shadow invoices: {e}")
        import traceback
        traceback.print_exc()
        shadow_invoices = None
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ETAPA 6: EXIBIR RESULTADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "="*70)
    print("📊 RESULTADOS FINAIS")
    print("="*70)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESULTADO 1: TRANSAÇÕES PROCESSADAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n📋 TRANSAÇÕES PROCESSADAS (primeiras 10):")
    print("-"*70)
    
    df_display = categorized_df.select([
        "transaction_id",
        "amount",
        "description",
        "predicted_category",
        "ml_confidence",
        "transaction_type",
        "month",
        "day_of_week"
    ]).head(10)
    
    print(df_display)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESULTADO 2: ESTATÍSTICAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n📈 ESTATÍSTICAS:")
    print("-"*70)
    
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
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESULTADO 3: SHADOW INVOICES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if shadow_invoices is not None and not shadow_invoices.is_empty():
        print("\n💰 SHADOW INVOICES (Obrigações Futuras):")
        print("-"*70)
        print(shadow_invoices)
        
        # Totais por tipo
        total_subscriptions = shadow_invoices.filter(
            shadow_invoices["type"] == "SUBSCRIPTION"
        )["amount"].sum()
        
        total_installments = shadow_invoices.filter(
            shadow_invoices["type"] == "INSTALLMENT"
        )["amount"].sum()
        
        print(f"\n💳 Impacto mensal estimado:")
        print(f"   Assinaturas:   R$ {abs(total_subscriptions):,.2f}")
        print(f"   Parcelamentos: R$ {abs(total_installments):,.2f}")
        print(f"   TOTAL:         R$ {abs(total_subscriptions + total_installments):,.2f}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONCLUSÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "="*70)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("="*70)
    
    print("\n📊 RESUMO DO PIPELINE:")
    print(f"   1. Pluggy:           {len(raw_transactions)} transações recebidas")
    print(f"   2. Validação:        {batch_result.total_valid} válidas")
    print(f"   3. Ingestor:         {metrics.records_after_dedup} únicas")
    print(f"   4. Classifier:       {len(categorized_df)} categorizadas")
    if shadow_invoices is not None and not shadow_invoices.is_empty():
        print(f"   5. Shadow Invoices:  {len(shadow_invoices)} detectadas")
    else:
        print(f"   5. Shadow Invoices:  0 detectadas")
    
    print("\n" + "="*70)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUTAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    test_complete_etl_pipeline()