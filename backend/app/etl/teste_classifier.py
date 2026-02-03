"""
🧪 TESTE DO CLASSIFIER - Transações Brasileiras Reais

Testa classificação com dados autênticos do mercado BR.

Como executar:
    cd /Users/gabriel-abel/projetoNexa/codigos-nexa-16
    pyenv shell 3.12.1
    python backend/app/etl/test_classifier.py
"""

import sys
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIX PYTHONPATH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import polars as pl
from app.etl.classifier import (
    TransactionClassifier,
    print_category_stats
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DADOS DE TESTE (Transações Reais BR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST_TRANSACTIONS = [
    # ━━━ ALIMENTAÇÃO ━━━
    {
        "description": "IFOOD *PEDIDO DELIVERY",
        "merchant": "ifood",
        "amount": -45.80,
        "expected_category": "Alimentação",
        "expected_confidence_min": 0.90
    },
    {
        "description": "COMPRA NO DÉBITO - UBER EATS SAO PAULO",
        "merchant": "uber eats",
        "amount": -32.50,
        "expected_category": "Alimentação",
        "expected_confidence_min": 0.90
    },
    {
        "description": "CARREFOUR SUPERMERCADO",
        "merchant": "carrefour",
        "amount": -234.56,
        "expected_category": "Alimentação",
        "expected_confidence_min": 0.85
    },
    {
        "description": "MCDONALDS SHOPPING CENTER",
        "merchant": "mcdonalds",
        "amount": -28.90,
        "expected_category": "Alimentação",
        "expected_confidence_min": 0.90
    },
    {
        "description": "RESTAURANTE PIZZARIA BELLA NAPOLI",
        "merchant": None,
        "amount": -89.00,
        "expected_category": "Alimentação",
        "expected_confidence_min": 0.85
    },
    
    # ━━━ TRANSPORTE ━━━
    {
        "description": "UBER *VIAGEM SAO PAULO",
        "merchant": "uber",
        "amount": -23.40,
        "expected_category": "Transporte",
        "expected_confidence_min": 0.90
    },
    {
        "description": "99 TAXI CORRIDA CENTRO",
        "merchant": "99",
        "amount": -18.75,
        "expected_category": "Transporte",
        "expected_category": "Transporte",
        "expected_confidence_min": 0.90
    },
    {
        "description": "POSTO SHELL GASOLINA",
        "merchant": "shell",
        "amount": -320.00,
        "expected_category": "Transporte",
        "expected_confidence_min": 0.85
    },
    {
        "description": "ESTACIONAMENTO SHOPPING",
        "merchant": None,
        "amount": -15.00,
        "expected_category": "Transporte",
        "expected_confidence_min": 0.85
    },
    
    # ━━━ SAÚDE ━━━
    {
        "description": "FARMACIA DROGARIA SAO PAULO",
        "merchant": "drogaria sao paulo",
        "amount": -67.80,
        "expected_category": "Saúde",
        "expected_confidence_min": 0.90
    },
    {
        "description": "DROGA RAIA MEDICAMENTO",
        "merchant": "droga raia",
        "amount": -45.90,
        "expected_category": "Saúde",
        "expected_confidence_min": 0.90
    },
    {
        "description": "CONSULTA MEDICA DR SILVA",
        "merchant": None,
        "amount": -250.00,
        "expected_category": "Saúde",
        "expected_confidence_min": 0.85
    },
    {
        "description": "UNIMED PLANO DE SAUDE",
        "merchant": "unimed",
        "amount": -450.00,
        "expected_category": "Saúde",
        "expected_confidence_min": 0.90
    },
    
    # ━━━ EDUCAÇÃO ━━━
    {
        "description": "UDEMY CURSO ONLINE PYTHON",
        "merchant": "udemy",
        "amount": -89.90,
        "expected_category": "Educação",
        "expected_confidence_min": 0.90
    },
    {
        "description": "MENSALIDADE FACULDADE ESTACIO",
        "merchant": None,
        "amount": -1200.00,
        "expected_category": "Educação",
        "expected_confidence_min": 0.85
    },
    {
        "description": "LIVRARIA SARAIVA LIVROS",
        "merchant": "saraiva",
        "amount": -78.50,
        "expected_category": "Educação",
        "expected_confidence_min": 0.85
    },
    
    # ━━━ LAZER ━━━
    {
        "description": "NETFLIX.COM *ASSINATURA PREMIUM",
        "merchant": "netflix",
        "amount": -49.90,
        "expected_category": "Lazer",
        "expected_confidence_min": 0.90
    },
    {
        "description": "SPOTIFY *PREMIUM",
        "merchant": "spotify",
        "amount": -21.90,
        "expected_category": "Lazer",
        "expected_confidence_min": 0.90
    },
    {
        "description": "AMAZON PRIME VIDEO",
        "merchant": "amazon",
        "amount": -14.90,
        "expected_category": "Lazer",
        "expected_confidence_min": 0.90
    },
    {
        "description": "INGRESSO CINEMA CINEMARK",
        "merchant": "cinemark",
        "amount": -38.00,
        "expected_category": "Lazer",
        "expected_confidence_min": 0.85
    },
    {
        "description": "SMARTFIT ACADEMIA",
        "merchant": "smartfit",
        "amount": -79.90,
        "expected_category": "Lazer",
        "expected_confidence_min": 0.85
    },
    
    # ━━━ MORADIA ━━━
    {
        "description": "ALUGUEL APARTAMENTO JANEIRO",
        "merchant": None,
        "amount": -1500.00,
        "expected_category": "Moradia",
        "expected_confidence_min": 0.90
    },
    {
        "description": "ENEL CONTA DE LUZ",
        "merchant": "enel",
        "amount": -234.56,
        "expected_category": "Moradia",
        "expected_confidence_min": 0.90
    },
    {
        "description": "SABESP CONTA AGUA",
        "merchant": "sabesp",
        "amount": -89.00,
        "expected_category": "Moradia",
        "expected_confidence_min": 0.90
    },
    {
        "description": "CLARO INTERNET BANDA LARGA",
        "merchant": "claro",
        "amount": -129.90,
        "expected_category": "Moradia",
        "expected_confidence_min": 0.90
    },
    {
        "description": "CONDOMINIO EDIFICIO",
        "merchant": None,
        "amount": -450.00,
        "expected_category": "Moradia",
        "expected_confidence_min": 0.90
    },
    
    # ━━━ VESTUÁRIO ━━━
    {
        "description": "ZARA ROUPAS",
        "merchant": "zara",
        "amount": -189.90,
        "expected_category": "Vestuário",
        "expected_confidence_min": 0.90
    },
    {
        "description": "NIKE TENIS ESPORTIVO",
        "merchant": "nike",
        "amount": -299.00,
        "expected_category": "Vestuário",
        "expected_confidence_min": 0.90
    },
    {
        "description": "RENNER LOJA DEPARTAMENTO",
        "merchant": "renner",
        "amount": -123.45,
        "expected_category": "Vestuário",
        "expected_confidence_min": 0.90
    },
    
    # ━━━ TRANSFERÊNCIAS ━━━
    {
        "description": "PIX ENVIADO PARA MARIA SILVA",
        "merchant": None,
        "amount": -100.00,
        "expected_category": "Transferências",
        "expected_confidence_min": 0.90
    },
    {
        "description": "TED RECEBIDA - JOAO SANTOS CPF",
        "merchant": None,
        "amount": 500.00,
        "expected_category": "Transferências",
        "expected_confidence_min": 0.85
    },
    {
        "description": "PICPAY TRANSFERENCIA",
        "merchant": "picpay",
        "amount": -50.00,
        "expected_category": "Transferências",
        "expected_confidence_min": 0.90
    },
    
    # ━━━ INVESTIMENTOS ━━━
    {
        "description": "XP INVESTIMENTOS CORRETORA",
        "merchant": "xp",
        "amount": -1000.00,
        "expected_category": "Investimentos",
        "expected_confidence_min": 0.90
    },
    {
        "description": "APLICACAO CDB BANCO INTER",
        "merchant": "inter",
        "amount": -5000.00,
        "expected_category": "Investimentos",
        "expected_confidence_min": 0.85
    },
    {
        "description": "RENDIMENTO POUPANCA",
        "merchant": None,
        "amount": 12.34,
        "expected_category": "Investimentos",
        "expected_confidence_min": 0.85
    },
    
    # ━━━ OUTROS (Edge Cases) ━━━
    {
        "description": "COMPRA DESCONHECIDA",
        "merchant": None,
        "amount": -100.00,
        "expected_category": "Outros",
        "expected_confidence_min": 0.40
    },
    {
        "description": "PAG ELETRONICO",
        "merchant": None,
        "amount": -50.00,
        "expected_category": "Outros",
        "expected_confidence_min": 0.40
    },
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_section(title: str):
    print("\n" + "=" * 80)
    print(f"🧪 {title}")
    print("=" * 80)


def print_test_result(passed: bool, message: str):
    icon = "✅" if passed else "❌"
    print(f"   {icon} {message}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_1_basic_classification():
    """Testa classificação básica com keywords."""
    print_section("TESTE 1: Classificação Básica")
    
    # Criar DataFrame
    df = pl.DataFrame([
        {
            "description": t["description"],
            "merchant": t["merchant"],
            "amount": t["amount"]
        }
        for t in TEST_TRANSACTIONS
    ])
    
    print(f"📥 {len(df)} transações carregadas")
    
    # Classificar
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(df)
    
    print(f"✅ Classificação concluída")
    print(f"\n📋 Amostra:")
    print(result.select([
        "description",
        "predicted_category",
        "confidence"
    ]).head(5))
    
    # Validar
    assert "predicted_category" in result.columns
    assert "confidence" in result.columns
    assert "category_source" in result.columns
    
    print_test_result(True, "Colunas corretas adicionadas")
    
    return result


def test_2_category_accuracy():
    """Testa precisão das categorias preditas."""
    print_section("TESTE 2: Precisão de Categorias")
    
    # Criar DataFrame com expected categories
    df = pl.DataFrame(TEST_TRANSACTIONS)
    
    # Classificar
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(df)
    
    # Comparar com expected
    correct = 0
    total = len(TEST_TRANSACTIONS)
    
    print("\n📊 Validação Detalhada:")
    print("-" * 80)
    
    for i, test in enumerate(TEST_TRANSACTIONS):
        predicted = result["predicted_category"][i]
        expected = test["expected_category"]
        confidence = result["confidence"][i]
        
        is_correct = predicted == expected
        if is_correct:
            correct += 1
        
        # Print detalhes (primeiros 10)
        if i < 10:
            status = "✅" if is_correct else "❌"
            desc_short = test["description"][:40]
            print(
                f"{status} {desc_short:<42} "
                f"Pred: {predicted:<15} "
                f"Exp: {expected:<15} "
                f"Conf: {confidence:.2f}"
            )
    
    accuracy = (correct / total) * 100
    
    print("-" * 80)
    print(f"\n📈 RESULTADO:")
    print(f"   Corretas: {correct}/{total}")
    print(f"   Accuracy: {accuracy:.1f}%")
    
    # Validar
    assert accuracy >= 85, f"Accuracy baixo: {accuracy:.1f}% (esperado >= 85%)"
    
    print_test_result(
        accuracy >= 85,
        f"Accuracy aceitável: {accuracy:.1f}% >= 85%"
    )


def test_3_confidence_levels():
    """Testa níveis de confiança."""
    print_section("TESTE 3: Níveis de Confiança")
    
    df = pl.DataFrame(TEST_TRANSACTIONS)
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(df)
    
    # Estatísticas de confidence
    avg_confidence = result["confidence"].mean()
    min_confidence = result["confidence"].min()
    max_confidence = result["confidence"].max()
    
    print(f"\n📊 Estatísticas de Confiança:")
    print(f"   Média:   {avg_confidence:.2f}")
    print(f"   Mínima:  {min_confidence:.2f}")
    print(f"   Máxima:  {max_confidence:.2f}")
    
    # Distribuição
    high_conf = result.filter(pl.col("confidence") >= 0.90).height
    med_conf = result.filter(
        (pl.col("confidence") >= 0.70) & (pl.col("confidence") < 0.90)
    ).height
    low_conf = result.filter(pl.col("confidence") < 0.70).height
    
    print(f"\n📈 Distribuição:")
    print(f"   Alta (>= 0.90):   {high_conf} ({high_conf/len(df)*100:.1f}%)")
    print(f"   Média (0.70-0.89): {med_conf} ({med_conf/len(df)*100:.1f}%)")
    print(f"   Baixa (< 0.70):    {low_conf} ({low_conf/len(df)*100:.1f}%)")
    
    # Validar
    assert avg_confidence >= 0.80, "Confiança média baixa"
    
    print_test_result(
        avg_confidence >= 0.80,
        f"Confiança média adequada: {avg_confidence:.2f} >= 0.80"
    )


def test_4_edge_cases():
    """Testa casos extremos."""
    print_section("TESTE 4: Casos Extremos")
    
    edge_cases = pl.DataFrame({
        "description": [
            "",  # Vazio
            "   ",  # Apenas espaços
            "XPTO 123",  # Desconhecido
            "ABC DEF GHI",  # Genérico
        ],
        "merchant": [None, None, None, None],
        "amount": [-100.0, -50.0, -30.0, -20.0]
    })
    
    print(f"📥 {len(edge_cases)} edge cases")
    
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(edge_cases)
    
    print(f"\n📋 Resultados:")
    print(result.select(["description", "predicted_category", "confidence"]))
    
    # Validar: Todos devem ser "Outros" com confiança baixa
    all_others = (result["predicted_category"] == "Outros").all()
    all_low_conf = (result["confidence"] <= 0.60).all()
    
    print_test_result(all_others, "Todos classificados como 'Outros'")
    print_test_result(all_low_conf, "Todas com confiança baixa (<= 0.60)")
    
    assert all_others
    assert all_low_conf


def test_5_category_distribution():
    """Testa distribuição de categorias."""
    print_section("TESTE 5: Distribuição de Categorias")
    
    df = pl.DataFrame(TEST_TRANSACTIONS)
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(df)
    
    # Exibir estatísticas
    print_category_stats(result)
    
    # Validar: Deve haver pelo menos 5 categorias diferentes
    unique_categories = result["predicted_category"].n_unique()
    
    print_test_result(
        unique_categories >= 5,
        f"{unique_categories} categorias únicas (esperado >= 5)"
    )
    
    assert unique_categories >= 5


def test_6_empty_dataframe():
    """Testa DataFrame vazio."""
    print_section("TESTE 6: DataFrame Vazio")
    
    empty_df = pl.DataFrame({
        "description": [],
        "merchant": [],
        "amount": []
    })
    
    print(f"📥 DataFrame vazio: {len(empty_df)} linhas")
    
    classifier = TransactionClassifier(mode="RULES")
    result = classifier.predict(empty_df)
    
    print(f"✅ Processado sem erros")
    print(f"   Colunas: {result.columns}")
    
    # Validar: Deve retornar DataFrame vazio com colunas corretas
    assert len(result) == 0
    assert "predicted_category" in result.columns
    assert "confidence" in result.columns
    
    print_test_result(True, "DataFrame vazio retorna colunas corretas")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_all_tests():
    print("\n" + "🚀" * 40)
    print("🧪 TESTE COMPLETO DO CLASSIFIER")
    print("🚀" * 40)
    
    try:
        test_1_basic_classification()
        test_2_category_accuracy()
        test_3_confidence_levels()
        test_4_edge_cases()
        test_5_category_distribution()
        test_6_empty_dataframe()
        
        print("\n" + "=" * 80)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 80)
        
        print("\n📋 RESUMO:")
        print(f"   ✅ Classificação básica funciona")
        print(f"   ✅ Accuracy >= 85%")
        print(f"   ✅ Confiança média >= 0.80")
        print(f"   ✅ Edge cases tratados corretamente")
        print(f"   ✅ Distribuição de categorias adequada")
        print(f"   ✅ DataFrame vazio tratado corretamente")
        
        print("\n🎯 PRÓXIMOS PASSOS:")
        print("   1. Integrar com Ingestor (pipeline completo)")
        print("   2. Coletar dados rotulados (treinar CatBoost)")
        print("   3. Implementar modo ML (quando tiver modelo)")
        print("   4. Implementar modo HYBRID (regras + ML)")
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERRO NO TESTE!")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)