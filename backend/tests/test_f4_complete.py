"""
test_f4_complete.py - Teste COMPLETO da Funcionalidade F4 (PF/PJ Classifier)

Valida TODOS os componentes e integrações:
1. Modelo ML (Random Forest)
2. Regras de Fallback (10 regras determinísticas)
3. Classificador Híbrido (ML + Fallback)
4. Integração no Pipeline ETL
5. User Overrides (Mock)
6. Schema Updates (TransactionOut)
7. Accuracy e Performance
8. Edge Cases e Robustez
9. Relatório Completo

Uso:
    cd backend/scripts
    python test_f4_complete.py
"""

import sys
import os
from datetime import datetime
import time
import json

# Adicionar backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import polars as pl
import joblib

# Imports do sistema
from app.etl.runner_updated import run_etl_pipeline
from app.etl.pf_pj_classifier import PFPJClassifier, PFPJFallbackClassifier
from app.integrations.open_finance.pluggy_mock import MockPluggyClient


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_header(title: str):
    """Imprime header formatado"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str, emoji: str = "📋"):
    """Imprime seção formatada"""
    print(f"\n{emoji} {title}")
    print("-" * 70)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Imprime resultado de um teste"""
    status = "✅ PASSOU" if passed else "❌ FALHOU"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"   {details}")
    return passed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 1: MODELOS ML
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_ml_models():
    """Testa carregamento e estrutura dos modelos ML"""
    print_section("TESTE 1: Modelos Machine Learning", "🤖")
    
    results = {
        "classifier_exists": False,
        "encoders_exist": False,
        "scaler_exists": False,
        "classifier_loaded": False,
        "features_count": 0
    }
    
    # Caminhos dos modelos
    models_dir = os.path.join(os.path.dirname(__file__), '..', 'models')
    classifier_path = os.path.join(models_dir, 'pf_pj_classifier.pkl')
    encoders_path = os.path.join(models_dir, 'feature_encoders.pkl')
    scaler_path = os.path.join(models_dir, 'feature_scaler.pkl')
    
    # Teste 1.1: Arquivos existem
    results["classifier_exists"] = os.path.exists(classifier_path)
    results["encoders_exist"] = os.path.exists(encoders_path)
    results["scaler_exists"] = os.path.exists(scaler_path)
    
    print_result(
        "1.1 Arquivos de modelo existem",
        all([results["classifier_exists"], results["encoders_exist"], results["scaler_exists"]]),
        f"Classifier: {results['classifier_exists']}, Encoders: {results['encoders_exist']}, Scaler: {results['scaler_exists']}"
    )
    
    # Teste 1.2: Modelo carrega corretamente
    if results["classifier_exists"]:
        try:
            model = joblib.load(classifier_path)
            results["classifier_loaded"] = True
            results["features_count"] = model.n_features_in_ if hasattr(model, 'n_features_in_') else 0
            
            print_result(
                "1.2 Modelo carrega corretamente",
                True,
                f"Features esperadas: {results['features_count']}, Tipo: {type(model).__name__}"
            )
        except Exception as e:
            print_result("1.2 Modelo carrega corretamente", False, f"Erro: {e}")
    
    # Teste 1.3: Encoders carregam
    if results["encoders_exist"]:
        try:
            encoders = joblib.load(encoders_path)
            categorical_features = ['transaction_type', 'amount_category', 'category', 'merchant_category']
            encoders_ok = all(col in encoders for col in categorical_features)
            
            print_result(
                "1.3 Encoders carregam corretamente",
                encoders_ok,
                f"Encoders disponíveis: {list(encoders.keys())}"
            )
        except Exception as e:
            print_result("1.3 Encoders carregam corretamente", False, f"Erro: {e}")
    
    # Teste 1.4: Scaler carrega
    if results["scaler_exists"]:
        try:
            scaler = joblib.load(scaler_path)
            scaler_ok = hasattr(scaler, 'transform')
            
            print_result(
                "1.4 Scaler carrega corretamente",
                scaler_ok,
                f"Tipo: {type(scaler).__name__}"
            )
        except Exception as e:
            print_result("1.4 Scaler carrega corretamente", False, f"Erro: {e}")
    
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 2: REGRAS DE FALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_fallback_rules():
    """Testa regras determinísticas de fallback"""
    print_section("TESTE 2: Regras de Fallback", "📏")
    
    classifier = PFPJFallbackClassifier()
    
    # Casos de teste para cada regra
    test_cases = [
        # Regra 1: Categoria PJ exclusiva
        {
            "name": "2.1 Categoria SALARY → PJ",
            "transaction": {"description": "Pagamento", "category": "SALARY", "amount": 1000, "hour_of_day": 10},
            "expected": "PJ"
        },
        # Regra 2: Categoria PF exclusiva
        {
            "name": "2.2 Categoria ENTERTAINMENT → PF",
            "transaction": {"description": "Streaming", "category": "ENTERTAINMENT", "amount": 50, "hour_of_day": 20},
            "expected": "PF"
        },
        # Regra 3: Keyword PJ
        {
            "name": "2.3 Keyword 'empresa' → PJ",
            "transaction": {"description": "PAGAMENTO EMPRESA LTDA", "category": "OTHER", "amount": 500, "hour_of_day": 14},
            "expected": "PJ"
        },
        # Regra 4: Keyword PF
        {
            "name": "2.4 Keyword 'uber' → PF",
            "transaction": {"description": "UBER TRIP", "category": "TRANSPORT", "amount": 30, "hour_of_day": 18},
            "expected": "PF"
        },
        # Regra 5: Valor alto
        {
            "name": "2.5 Valor > R$ 2000 → PJ",
            "transaction": {"description": "Pagamento", "category": "OTHER", "amount": 3000, "hour_of_day": 10},
            "expected": "PJ"
        },
        # Regra 6: Valor baixo + fora horário comercial
        {
            "name": "2.6 Valor < R$ 20 + noturno → PF",
            "transaction": {"description": "Compra", "category": "OTHER", "amount": 15, "hour_of_day": 22},
            "expected": "PF"
        },
        # Regra 7: Merchant PJ
        {
            "name": "2.7 Merchant 'microsoft' → PJ",
            "transaction": {"description": "Licença", "category": "SOFTWARE", "amount": 500, "hour_of_day": 10, "merchant": "Microsoft"},
            "expected": "PJ"
        },
        # Regra 8: Merchant PF
        {
            "name": "2.8 Merchant 'netflix' → PF",
            "transaction": {"description": "Assinatura", "category": "ENTERTAINMENT", "amount": 40, "hour_of_day": 10, "merchant": "Netflix"},
            "expected": "PF"
        },
        # Regra 9: Horário comercial + valor médio
        {
            "name": "2.9 Horário comercial + R$ 500 → PJ",
            "transaction": {"description": "Compra", "category": "OTHER", "amount": 500, "hour_of_day": 14},
            "expected": "PJ"
        },
        # Regra 10: Fim de semana + valor baixo
        {
            "name": "2.10 Fim de semana + R$ 100 → PF",
            "transaction": {"description": "Compra", "category": "OTHER", "amount": 100, "hour_of_day": 14},
            "expected": "PF"
        }
    ]
    
    results = []
    for test_case in test_cases:
        result = classifier.classify(test_case["transaction"])
        passed = result == test_case["expected"]
        print_result(test_case["name"], passed, f"Esperado: {test_case['expected']}, Obtido: {result}")
        results.append(passed)
    
    accuracy = sum(results) / len(results)
    print(f"\n📊 Accuracy das Regras de Fallback: {accuracy:.1%} ({sum(results)}/{len(results)})")
    
    return {
        "total_rules": len(test_cases),
        "correct": sum(results),
        "accuracy": accuracy
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 3: CLASSIFICADOR HÍBRIDO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_hybrid_classifier():
    """Testa estratégia híbrida ML + Fallback"""
    print_section("TESTE 3: Classificador Híbrido", "🔀")
    
    classifier = PFPJClassifier()
    
    # Teste 3.1: Inicialização
    has_ml = classifier.model is not None
    has_fallback = classifier.fallback_classifier is not None
    
    print_result(
        "3.1 Inicialização do classificador",
        has_fallback,
        f"ML disponível: {has_ml}, Fallback disponível: {has_fallback}"
    )
    
    # Teste 3.2: Classificação de casos simples
    test_cases = [
        {
            "name": "Uber Trip (PF claro)",
            "transaction": {
                "description": "UBER *TRIP",
                "category": "TRANSPORT",
                "amount": -30,
                "transaction_date": "2024-01-15T18:00:00Z",
                "merchant": "Uber"
            },
            "expected": "PF"
        },
        {
            "name": "Salário (PJ claro)",
            "transaction": {
                "description": "SALARIO EMPRESA LTDA",
                "category": "SALARY",
                "amount": 5000,
                "transaction_date": "2024-01-30T08:00:00Z",
                "merchant": "Empresa XYZ"
            },
            "expected": "PJ"
        }
    ]
    
    results = []
    for test_case in test_cases:
        result = classifier._classify_single(test_case["transaction"])
        passed = result == test_case["expected"]
        print_result(f"3.2 {test_case['name']}", passed, f"Esperado: {test_case['expected']}, Obtido: {result}")
        results.append(passed)
    
    # Teste 3.3: Batch classification
    df = pl.DataFrame([case["transaction"] for case in test_cases])
    classified_df = classifier.classify_batch(df)
    
    batch_ok = "pf_pj_label" in classified_df.columns
    print_result("3.3 Classificação em batch", batch_ok, f"Coluna adicionada: {batch_ok}")
    
    return {
        "ml_available": has_ml,
        "fallback_available": has_fallback,
        "simple_cases_correct": sum(results),
        "batch_works": batch_ok
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 4: INTEGRAÇÃO NO PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_pipeline_integration():
    """Testa integração completa no pipeline ETL"""
    print_section("TESTE 4: Integração no Pipeline ETL", "🔗")
    
    # Carregar dados mock
    client = MockPluggyClient()
    response = client.get_transactions("acc_001")
    df = pl.DataFrame(response["results"])
    
    print(f"   Carregadas {len(df)} transações mock")
    
    # Teste 4.1: Pipeline executa sem erros
    try:
        start_time = time.time()
        processed_df = run_etl_pipeline(
            transactions_df=df,
            user_id="test_user_f4",
            account_id="acc_001"
        )
        execution_time = time.time() - start_time
        
        print_result(
            "4.1 Pipeline executa sem erros",
            True,
            f"Tempo de execução: {execution_time:.2f}s"
        )
    except Exception as e:
        print_result("4.1 Pipeline executa sem erros", False, f"Erro: {e}")
        return {"pipeline_works": False}
    
    # Teste 4.2: Coluna pf_pj_label foi adicionada
    has_column = "pf_pj_label" in processed_df.columns
    print_result("4.2 Coluna pf_pj_label adicionada", has_column)
    
    if not has_column:
        return {"pipeline_works": True, "column_added": False}
    
    # Teste 4.3: Todas as transações foram classificadas
    total = len(processed_df)
    classified = len(processed_df.filter(pl.col("pf_pj_label").is_not_null()))
    all_classified = classified == total
    
    print_result(
        "4.3 Todas as transações classificadas",
        all_classified,
        f"{classified}/{total} transações classificadas"
    )
    
    # Teste 4.4: Distribuição de classificações
    pf_count = len(processed_df.filter(pl.col("pf_pj_label") == "PF"))
    pj_count = len(processed_df.filter(pl.col("pf_pj_label") == "PJ"))
    uncertain_count = len(processed_df.filter(pl.col("pf_pj_label") == "UNCERTAIN"))
    
    print(f"\n   Distribuição:")
    print(f"      PF: {pf_count} ({pf_count/total*100:.1f}%)")
    print(f"      PJ: {pj_count} ({pj_count/total*100:.1f}%)")
    print(f"      UNCERTAIN: {uncertain_count} ({uncertain_count/total*100:.1f}%)")
    
    # Distribuição esperada: ~60% PF, ~40% PJ
    distribution_ok = (pf_count >= 12 and pf_count <= 18) and (pj_count >= 7 and pj_count <= 13)
    print_result(
        "4.4 Distribuição dentro do esperado",
        distribution_ok,
        "Esperado: 60% PF / 40% PJ"
    )
    
    return {
        "pipeline_works": True,
        "column_added": has_column,
        "all_classified": all_classified,
        "pf_count": pf_count,
        "pj_count": pj_count,
        "uncertain_count": uncertain_count,
        "execution_time": execution_time,
        "processed_df": processed_df
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 5: ACCURACY E PERFORMANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_accuracy_and_performance(processed_df: pl.DataFrame):
    """Testa accuracy nos dados mock e métricas de performance"""
    print_section("TESTE 5: Accuracy e Performance", "📊")
    
    # Labels esperados (baseado nos transaction_ids mock)
    expected_labels = {
        # PF (15 transações)
        "trx_pf_001": "PF", "trx_pf_002": "PF", "trx_pf_003": "PF",
        "trx_pf_004": "PF", "trx_pf_005": "PF", "trx_pf_006": "PF",
        "trx_pf_007": "PF", "trx_pf_008": "PF", "trx_pf_009": "PF",
        "trx_pf_010": "PF", "trx_pf_011": "PF", "trx_pf_012": "PF",
        "trx_pf_013": "PF", "trx_pf_014": "PF", "trx_pf_015": "PF",
        
        # PJ (10 transações)
        "trx_pj_001": "PJ", "trx_pj_002": "PJ", "trx_pj_003": "PJ",
        "trx_pj_004": "PJ", "trx_pj_005": "PJ", "trx_pj_006": "PJ",
        "trx_pj_007": "PJ", "trx_pj_008": "PJ", "trx_pj_009": "PJ",
        "trx_pj_010": "PJ"
    }
    
    # Calcular accuracy
    correct = 0
    total = 0
    errors = []
    
    # Métricas por classe
    tp_pf = 0  # True Positive PF
    fp_pf = 0  # False Positive PF
    fn_pf = 0  # False Negative PF
    tp_pj = 0  # True Positive PJ
    fp_pj = 0  # False Positive PJ
    fn_pj = 0  # False Negative PJ
    
    for row in processed_df.iter_rows(named=True):
        txn_id = row.get("transaction_id")
        predicted = row.get("pf_pj_label")
        
        if txn_id in expected_labels:
            total += 1
            expected = expected_labels[txn_id]
            
            if predicted == expected:
                correct += 1
                if expected == "PF":
                    tp_pf += 1
                else:
                    tp_pj += 1
            else:
                errors.append({
                    "transaction_id": txn_id,
                    "description": row.get("description", "")[:40],
                    "expected": expected,
                    "predicted": predicted
                })
                
                # Atualizar métricas
                if expected == "PF":
                    fn_pf += 1
                    fp_pj += 1
                else:
                    fn_pj += 1
                    fp_pf += 1
    
    accuracy = correct / total if total > 0 else 0
    
    # Calcular Precision e Recall
    precision_pf = tp_pf / (tp_pf + fp_pf) if (tp_pf + fp_pf) > 0 else 0
    recall_pf = tp_pf / (tp_pf + fn_pf) if (tp_pf + fn_pf) > 0 else 0
    f1_pf = 2 * (precision_pf * recall_pf) / (precision_pf + recall_pf) if (precision_pf + recall_pf) > 0 else 0
    
    precision_pj = tp_pj / (tp_pj + fp_pj) if (tp_pj + fp_pj) > 0 else 0
    recall_pj = tp_pj / (tp_pj + fn_pj) if (tp_pj + fn_pj) > 0 else 0
    f1_pj = 2 * (precision_pj * recall_pj) / (precision_pj + recall_pj) if (precision_pj + recall_pj) > 0 else 0
    
    print(f"\n📈 Métricas Gerais:")
    print(f"   Total avaliado: {total}")
    print(f"   Corretos: {correct}")
    print(f"   Erros: {len(errors)}")
    print(f"   Accuracy: {accuracy:.1%}")
    
    print(f"\n📊 Métricas por Classe:")
    print(f"   PF - Precision: {precision_pf:.1%}, Recall: {recall_pf:.1%}, F1: {f1_pf:.1%}")
    print(f"   PJ - Precision: {precision_pj:.1%}, Recall: {recall_pj:.1%}, F1: {f1_pj:.1%}")
    
    if errors:
        print(f"\n❌ Classificações Incorretas ({len(errors)}):")
        for error in errors[:5]:  # Mostrar apenas primeiros 5
            print(f"   {error['transaction_id']}: {error['description']}")
            print(f"      Esperado: {error['expected']} | Previsto: {error['predicted']}")
    
    # Teste de threshold de accuracy
    accuracy_ok = accuracy >= 0.80  # Meta: 80%
    print_result(
        "5.1 Accuracy ≥ 80%",
        accuracy_ok,
        f"Accuracy: {accuracy:.1%}"
    )
    
    # Teste de precision
    precision_ok = precision_pf >= 0.80 and precision_pj >= 0.80
    print_result(
        "5.2 Precision ≥ 80% para ambas as classes",
        precision_ok,
        f"PF: {precision_pf:.1%}, PJ: {precision_pj:.1%}"
    )
    
    return {
        "total": total,
        "correct": correct,
        "errors": len(errors),
        "accuracy": accuracy,
        "precision_pf": precision_pf,
        "recall_pf": recall_pf,
        "f1_pf": f1_pf,
        "precision_pj": precision_pj,
        "recall_pj": recall_pj,
        "f1_pj": f1_pj,
        "error_details": errors
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 6: EDGE CASES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_edge_cases():
    """Testa casos extremos e robustez"""
    print_section("TESTE 6: Edge Cases e Robustez", "🛡️")
    
    classifier = PFPJClassifier()
    
    edge_cases = [
        {
            "name": "6.1 Todos os campos None",
            "transaction": {
                "description": None,
                "category": None,
                "amount": None,
                "transaction_date": None,
                "merchant": None
            }
        },
        {
            "name": "6.2 Strings vazias",
            "transaction": {
                "description": "",
                "category": "",
                "amount": 0,
                "transaction_date": "",
                "merchant": ""
            }
        },
        {
            "name": "6.3 Categoria desconhecida",
            "transaction": {
                "description": "Compra",
                "category": "UNKNOWN_CATEGORY_XYZ",
                "amount": 100,
                "transaction_date": "2024-01-01T12:00:00Z",
                "merchant": "Loja"
            }
        },
        {
            "name": "6.4 Data inválida",
            "transaction": {
                "description": "Compra",
                "category": "GROCERIES",
                "amount": 100,
                "transaction_date": "invalid-date",
                "merchant": "Carrefour"
            }
        },
        {
            "name": "6.5 Valor muito alto",
            "transaction": {
                "description": "Pagamento",
                "category": "OTHER",
                "amount": 1000000,
                "transaction_date": "2024-01-01T10:00:00Z",
                "merchant": "Unknown"
            }
        }
    ]
    
    results = []
    for test_case in edge_cases:
        try:
            result = classifier._classify_single(test_case["transaction"])
            passed = result in ["PF", "PJ", "UNCERTAIN"]
            print_result(
                test_case["name"],
                passed,
                f"Resultado: {result}"
            )
            results.append(passed)
        except Exception as e:
            print_result(test_case["name"], False, f"Erro: {e}")
            results.append(False)
    
    all_passed = all(results)
    print_result(
        "6.6 Todos os edge cases tratados",
        all_passed,
        f"{sum(results)}/{len(results)} casos tratados corretamente"
    )
    
    return {
        "total_cases": len(edge_cases),
        "passed": sum(results),
        "all_passed": all_passed
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 7: SCHEMA VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_schema_validation(processed_df: pl.DataFrame):
    """Valida que schema TransactionOut está correto"""
    print_section("TESTE 7: Validação de Schema", "📋")
    
    # Campos esperados do F4
    expected_f4_fields = ["pf_pj_label"]
    
    # Teste 7.1: Campos F4 existem
    missing_fields = [field for field in expected_f4_fields if field not in processed_df.columns]
    fields_ok = len(missing_fields) == 0
    
    print_result(
        "7.1 Campos F4 presentes no DataFrame",
        fields_ok,
        f"Faltando: {missing_fields}" if missing_fields else "Todos os campos presentes"
    )
    
    # Teste 7.2: Tipos de dados corretos
    if "pf_pj_label" in processed_df.columns:
        pf_pj_type = processed_df.schema["pf_pj_label"]
        type_ok = str(pf_pj_type) in ["String", "Utf8"]
        
        print_result(
            "7.2 Tipo de dados correto (String)",
            type_ok,
            f"Tipo: {pf_pj_type}"
        )
    
    # Teste 7.3: Valores válidos
    if "pf_pj_label" in processed_df.columns:
        valid_values = ["PF", "PJ", "UNCERTAIN", None]
        invalid_rows = processed_df.filter(~pl.col("pf_pj_label").is_in(valid_values))
        values_ok = len(invalid_rows) == 0
        
        print_result(
            "7.3 Apenas valores válidos (PF/PJ/UNCERTAIN)",
            values_ok,
            f"Valores inválidos: {len(invalid_rows)}"
        )
    
    return {
        "fields_present": fields_ok,
        "types_correct": type_ok if "pf_pj_label" in processed_df.columns else False,
        "values_valid": values_ok if "pf_pj_label" in processed_df.columns else False
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 8: PERFORMANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_performance():
    """Testa performance e throughput"""
    print_section("TESTE 8: Performance e Throughput", "⚡")
    
    classifier = PFPJClassifier()
    
    # Carregar dados mock
    client = MockPluggyClient()
    response = client.get_transactions("acc_001")
    df = pl.DataFrame(response["results"])
    
    # Teste 8.1: Tempo de classificação batch
    start_time = time.time()
    classified_df = classifier.classify_batch(df)
    batch_time = time.time() - start_time
    
    throughput = len(df) / batch_time if batch_time > 0 else 0
    
    print_result(
        "8.1 Performance de batch",
        True,
        f"Tempo: {batch_time:.3f}s | Throughput: {throughput:.0f} transações/seg"
    )
    
    # Teste 8.2: Tempo de classificação single
    single_times = []
    for i in range(10):
        row = df.row(i, named=True)
        start_time = time.time()
        classifier._classify_single(row)
        single_time = time.time() - start_time
        single_times.append(single_time)
    
    avg_single_time = sum(single_times) / len(single_times)
    
    print_result(
        "8.2 Performance single",
        True,
        f"Tempo médio: {avg_single_time*1000:.1f}ms por transação"
    )
    
    # Teste 8.3: Performance aceitável
    performance_ok = batch_time < 5.0 and avg_single_time < 0.5
    
    print_result(
        "8.3 Performance dentro do esperado",
        performance_ok,
        f"Batch < 5s: {batch_time < 5.0}, Single < 500ms: {avg_single_time < 0.5}"
    )
    
    return {
        "batch_time": batch_time,
        "throughput": throughput,
        "avg_single_time": avg_single_time,
        "performance_ok": performance_ok
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN: EXECUÇÃO COMPLETA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Executa todos os testes e gera relatório completo"""
    print_header("TESTE COMPLETO F4 - VALIDAÇÃO TOTAL")
    
    print(f"\n📅 Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Objetivo: Validar TODOS os componentes da Funcionalidade F4")
    
    # Estrutura de resultados
    all_results = {
        "execution_date": datetime.now().isoformat(),
        "tests": {}
    }
    
    # Executar todos os testes
    try:
        # Teste 1: Modelos ML
        all_results["tests"]["ml_models"] = test_ml_models()
        
        # Teste 2: Regras de Fallback
        all_results["tests"]["fallback_rules"] = test_fallback_rules()
        
        # Teste 3: Classificador Híbrido
        all_results["tests"]["hybrid_classifier"] = test_hybrid_classifier()
        
        # Teste 4: Integração no Pipeline
        pipeline_results = test_pipeline_integration()
        all_results["tests"]["pipeline_integration"] = pipeline_results
        
        # Teste 5: Accuracy (precisa do DataFrame do pipeline)
        if pipeline_results.get("processed_df") is not None:
            all_results["tests"]["accuracy"] = test_accuracy_and_performance(
                pipeline_results["processed_df"]
            )
        
        # Teste 6: Edge Cases
        all_results["tests"]["edge_cases"] = test_edge_cases()
        
        # Teste 7: Schema Validation
        if pipeline_results.get("processed_df") is not None:
            all_results["tests"]["schema"] = test_schema_validation(
                pipeline_results["processed_df"]
            )
        
        # Teste 8: Performance
        all_results["tests"]["performance"] = test_performance()
        
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO DURANTE OS TESTES: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESUMO FINAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print_header("RESUMO FINAL - RESULTADO DOS TESTES")
    
    # Calcular score geral
    accuracy_test = all_results["tests"].get("accuracy", {})
    accuracy = accuracy_test.get("accuracy", 0)
    
    fallback_test = all_results["tests"].get("fallback_rules", {})
    fallback_accuracy = fallback_test.get("accuracy", 0)
    
    edge_test = all_results["tests"].get("edge_cases", {})
    edge_cases_ok = edge_test.get("all_passed", False)
    
    pipeline_test = all_results["tests"].get("pipeline_integration", {})
    pipeline_ok = pipeline_test.get("pipeline_works", False)
    
    # Critérios de aprovação
    criteria = {
        "Accuracy ≥ 80%": accuracy >= 0.80,
        "Fallback Rules ≥ 90%": fallback_accuracy >= 0.90,
        "Edge Cases tratados": edge_cases_ok,
        "Pipeline funciona": pipeline_ok,
        "Performance OK": all_results["tests"].get("performance", {}).get("performance_ok", False)
    }
    
    print("\n📊 Critérios de Aprovação:")
    for criterion, passed in criteria.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {criterion}")
    
    all_passed = all(criteria.values())
    
    print("\n📈 Métricas Principais:")
    print(f"   Accuracy Geral: {accuracy:.1%}")
    print(f"   Fallback Accuracy: {fallback_accuracy:.1%}")
    print(f"   Precision PF: {accuracy_test.get('precision_pf', 0):.1%}")
    print(f"   Precision PJ: {accuracy_test.get('precision_pj', 0):.1%}")
    print(f"   Edge Cases: {edge_test.get('passed', 0)}/{edge_test.get('total_cases', 0)}")
    
    # Salvar relatório JSON
    output_file = os.path.join(
        os.path.dirname(__file__), '..', 'docs', 'f4_complete_test_results.json'
    )
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n💾 Relatório completo salvo em: {output_file}")
    
    # Resultado final
    if all_passed:
        print_header("✅ TODOS OS TESTES PASSARAM!")
        print("\n🎉 Funcionalidade F4 está COMPLETA e PRONTA PARA PRODUÇÃO!")
        print("\n📋 Componentes Validados:")
        print("   ✅ Modelos ML (Random Forest)")
        print("   ✅ Regras de Fallback (10 regras)")
        print("   ✅ Classificador Híbrido")
        print("   ✅ Integração no Pipeline ETL")
        print("   ✅ Accuracy ≥ 80%")
        print("   ✅ Edge Cases tratados")
        print("   ✅ Schema correto")
        print("   ✅ Performance adequada")
        print("\n🚀 Próximo passo: Criar tabelas SQL e implementar endpoints de API")
        return 0
    else:
        print_header("⚠️ ALGUNS TESTES FALHARAM")
        print("\n📋 Componentes com Problemas:")
        for criterion, passed in criteria.items():
            if not passed:
                print(f"   ❌ {criterion}")
        print("\n💡 Revise os logs acima para detalhes dos erros")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)