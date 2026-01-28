"""
test_etl_imports.py - Testa se o módulo ETL foi criado corretamente

Execute:
    python test_etl_imports.py
"""

print("="*70)
print("🧪 TESTE 1: Importando módulo ETL")
print("="*70)

try:
    # Tenta importar o módulo
    from app.etl import (
        TransactionIngestor,
        TransactionClassifier,
        RecurringDetector,  # Vai falhar (ainda não criamos)
        DataQualityValidator  # Vai falhar (ainda não criamos)
    )
    print("✅ Módulo ETL importado com sucesso!")
    
except ImportError as e:
    print(f"❌ Erro ao importar: {e}")
    print("\n🔍 Vamos tentar importar apenas os arquivos que existem:")
    
    try:
        from app.etl import TransactionIngestor, TransactionClassifier
        print("✅ TransactionIngestor importado com sucesso!")
        print("✅ TransactionClassifier importado com sucesso!")
        print("\n⚠️  RecurringDetector e DataQualityValidator ainda não foram criados (normal)")
        
    except ImportError as e2:
        print(f"❌ Erro crítico: {e2}")
        print("\n💡 SOLUÇÃO:")
        print("   1. Verifique se os arquivos estão em backend/app/etl/")
        print("   2. Verifique se __init__.py existe e tem código")
        print("   3. Tente novamente")

print("\n" + "="*70)