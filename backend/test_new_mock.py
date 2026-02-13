#!/usr/bin/env python3
"""
Teste dos novos dados mock para F4
"""

from app.runner import NexaRunner

def test_new_mock_data():
    print("🧪 Testando novos dados mock para F4...")

    runner = NexaRunner(mode='dev')
    result = runner.run()

    print("✅ Pipeline executado com sucesso!")
    print(f"📊 Transações processadas: {len(result['transactions']['clean_df'])}")
    print(f"🏷️  Transações categorizadas: {len(result['transactions']['categorized_df'])}")
    print(f"🔄 Padrões recorrentes: {len(result['analysis']['recurring_patterns'])}")
    print(f"👻 Eventos shadow: {len(result['projections']['shadow_events'])}")

    # Mostrar algumas transações para verificar diversidade
    df = result['transactions']['categorized_df']
    print("\n📋 Amostra de transações categorizadas:")
    sample = df.head(10)
    for row in sample.iter_rows(named=True):
        print(f"  {row['description'][:30]:<30} | {row['predicted_category']:<15} | R$ {row['amount']:>8.2f}")

if __name__ == "__main__":
    test_new_mock_data()