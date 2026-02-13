"""
scripts/validate_pf_pj_classifier.py - Validação do Classificador PF/PJ com Dados Reais

Objetivo: Validar o classificador PF/PJ usando dados reais do sistema,
comparando com dados mock conhecidos e testando edge cases.

Validações:
1. Dados reais do DuckDB (se disponíveis)
2. Edge cases (valores None, categorias desconhecidas)
3. Robustez do modelo ML + fallback
4. Performance e confiança
"""

import polars as pl
import pandas as pd
import duckdb
import sys
import os
from datetime import datetime
import json

# Adicionar backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.etl.pf_pj_classifier import PFPJClassifier

def load_real_transactions():
    """Carrega transações reais do DuckDB"""
    try:
        conn = duckdb.connect(os.path.join(os.path.dirname(__file__), '..', 'data', 'transactions.duckdb'))
        df = conn.execute('SELECT * FROM transactions').fetchdf()
        conn.close()

        # Converte para polars
        real_df = pl.from_pandas(df)

        print(f"📊 Carregadas {len(real_df)} transações reais do DuckDB")
        return real_df

    except Exception as e:
        print(f"❌ Erro carregando dados reais: {e}")
        return None

def create_synthetic_test_cases():
    """Cria casos de teste sintéticos para validação"""
    test_cases = [
        # Casos PF claros
        {
            'description': 'Uber viagem centro',
            'merchant': 'Uber',
            'amount': -25.50,
            'category': 'TRANSPORT',
            'transaction_date': '2024-01-15T14:30:00Z',
            'expected': 'PF'
        },
        {
            'description': 'Netflix mensal',
            'merchant': 'Netflix',
            'amount': -39.90,
            'category': 'ENTERTAINMENT',
            'transaction_date': '2024-01-15T10:00:00Z',
            'expected': 'PF'
        },
        {
            'description': 'Compra Carrefour',
            'merchant': 'Carrefour',
            'amount': -89.30,
            'category': 'FOOD',
            'transaction_date': '2024-01-15T18:45:00Z',
            'expected': 'PF'
        },

        # Casos PJ claros
        {
            'description': 'Salário empresa ABC Ltda',
            'merchant': 'Empresa ABC Ltda',
            'amount': 5000.00,
            'category': 'SALARY',
            'transaction_date': '2024-01-30T08:00:00Z',
            'expected': 'PJ'
        },
        {
            'description': 'Aluguel escritório',
            'merchant': 'Imobiliaria XYZ',
            'amount': -2500.00,
            'category': 'RENT',
            'transaction_date': '2024-01-01T09:00:00Z',
            'expected': 'PJ'
        },
        {
            'description': 'Compra material escritório papelaria',
            'merchant': 'Papelaria Central',
            'amount': -450.00,
            'category': 'OFFICE_SUPPLIES',
            'transaction_date': '2024-01-10T11:30:00Z',
            'expected': 'PJ'
        },

        # Edge cases
        {
            'description': 'Transação sem categoria',
            'merchant': 'Unknown',
            'amount': -100.00,
            'category': None,  # Valor None
            'transaction_date': '2024-01-15T12:00:00Z',
            'expected': 'UNCERTAIN'
        },
        {
            'description': 'PIX recebido amigo',
            'merchant': 'João Silva',
            'amount': 200.00,
            'category': 'TRANSFER',
            'transaction_date': '2024-01-15T20:00:00Z',
            'expected': 'PF'
        },
        {
            'description': 'Compra corporativa',
            'merchant': 'Microsoft',
            'amount': -1500.00,
            'category': 'SOFTWARE',
            'transaction_date': '2024-01-15T14:00:00Z',
            'expected': 'PJ'
        }
    ]

    # Converte para DataFrame
    df_data = []
    for case in test_cases:
        df_data.append({
            'transaction_id': f"test_{len(df_data)+1}",
            'description': case['description'],
            'merchant': case['merchant'],
            'amount': case['amount'],
            'category': case['category'],
            'transaction_date': case['transaction_date'],
            'expected_pf_pj': case['expected']
        })

    test_df = pl.DataFrame(df_data)
    print(f"🧪 Criados {len(test_df)} casos de teste sintéticos")
    return test_df

def validate_classifier(classifier, transactions_df):
    """Valida o classificador com dados fornecidos"""
    print(f"\n🔍 Validando {len(transactions_df)} transações...")

    # Classifica
    classified_df = classifier.classify_batch(transactions_df)

    # Análise de resultados
    results = []

    for row in classified_df.iter_rows(named=True):
        transaction_id = row.get('transaction_id', 'N/A')
        predicted = row.get('pf_pj_label', 'UNKNOWN')
        expected = row.get('expected_pf_pj', 'N/A')
        description = row.get('description', '')

        # Verifica se acertou (se tem expected)
        correct = 'N/A'
        if expected != 'N/A' and expected in ['PF', 'PJ']:
            correct = '✅' if predicted == expected else '❌'

        results.append({
            'transaction_id': transaction_id,
            'description': description[:50],
            'predicted': predicted,
            'expected': expected,
            'correct': correct
        })

    # Estatísticas
    total = len(results)
    pf_count = sum(1 for r in results if r['predicted'] == 'PF')
    pj_count = sum(1 for r in results if r['predicted'] == 'PJ')
    uncertain_count = sum(1 for r in results if r['predicted'] == 'UNCERTAIN')

    correct_predictions = sum(1 for r in results if r['correct'] == '✅')
    total_expected = sum(1 for r in results if r['expected'] != 'N/A')
    accuracy = correct_predictions / total_expected if total_expected > 0 else 0

    print("\n📊 RESULTADOS DA VALIDAÇÃO")
    print("=" * 50)
    print(f"Total de transações: {total}")
    print(f"Classificadas como PF: {pf_count}")
    print(f"Classificadas como PJ: {pj_count}")
    print(f"Classificadas como UNCERTAIN: {uncertain_count}")
    print(f"Acurácia: {accuracy:.2f}")
    print(f"Previsões corretas: {correct_predictions}/{total_expected}")
    # Detalhes por transação
    print("\n📋 DETALHES POR TRANSAÇÃO")
    print("-" * 80)
    for result in results:
        print(f"{result['transaction_id']:<15} | {result['description']:<50} | {result['predicted']:<10} | {result['expected']:<10} | {result['correct']}")

    return results, {
        'total': total,
        'pf_count': pf_count,
        'pj_count': pj_count,
        'uncertain_count': uncertain_count,
        'accuracy': accuracy,
        'correct_predictions': correct_predictions
    }

def test_edge_cases():
    """Testa casos extremos e robustez"""
    print("\n🧪 TESTANDO EDGE CASES")

    classifier = PFPJClassifier()

    # Teste com dados None/inválidos
    edge_cases = [
        {'description': None, 'merchant': None, 'amount': None, 'category': None, 'transaction_date': None},
        {'description': '', 'merchant': '', 'amount': 0, 'category': '', 'transaction_date': ''},
        {'description': 'Transação normal', 'merchant': 'Loja', 'amount': -50, 'category': 'UNKNOWN_CATEGORY', 'transaction_date': '2024-01-01T12:00:00Z'},
    ]

    for i, case in enumerate(edge_cases):
        try:
            result = classifier._classify_single(case)
            print(f"  Edge case {i+1}: {result} ✅")
        except Exception as e:
            print(f"  Edge case {i+1}: ERRO - {e} ❌")

def main():
    """Função principal"""
    print("🎯 VALIDAÇÃO DO CLASSIFICADOR PF/PJ")
    print("=" * 60)

    # Inicializa classificador
    classifier = PFPJClassifier()

    # Testa edge cases primeiro
    test_edge_cases()

    # Carrega dados reais
    real_df = load_real_transactions()

    if real_df is not None and len(real_df) > 0:
        print("\n🔍 VALIDANDO COM DADOS REAIS")
        validate_classifier(classifier, real_df)
    else:
        print("\n⚠️  Dados reais insuficientes - pulando validação real")

    # Valida com casos sintéticos
    print("\n🧪 VALIDANDO COM CASOS SINTÉTICOS")
    synthetic_df = create_synthetic_test_cases()
    results, stats = validate_classifier(classifier, synthetic_df)

    # Salva resultados
    output_file = os.path.join(os.path.dirname(__file__), '..', 'docs', 'pf_pj_validation_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'validation_date': datetime.now().isoformat(),
            'synthetic_test_results': results,
            'statistics': stats
        }, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Resultados salvos em: {output_file}")

    # Conclusão
    accuracy = stats['accuracy']
    if accuracy >= 0.85:
        print("\n🎉 VALIDAÇÃO APROVADA!")
        print(f"   Acurácia: {accuracy:.2f}")
    elif accuracy >= 0.70:
        print("\n⚠️  VALIDAÇÃO RAZOÁVEL")
        print(f"   Acurácia: {accuracy:.2f}")
        print("   Recomendado: Mais dados de treino ou ajustes nas regras")
    else:
        print("\n❌ VALIDAÇÃO INSATISFATÓRIA")
        print(f"   Acurácia: {accuracy:.2f}")
        print("   Necessário: Revisar modelo, regras ou dados de treino")

    print("\n✅ Validação concluída!")

if __name__ == "__main__":
    main()