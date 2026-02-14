"""
quick_test_f4.py - Teste Rápido do Classificador PF/PJ

Teste minimalista para validar que o classificador está funcionando.

Uso:
    cd backend/scripts
    python quick_test_f4.py
"""

import sys
import os

# Adicionar backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import polars as pl
from app.etl.runner_updated import run_etl_pipeline
from app.integrations.open_finance.pluggy_mock import MockPluggyClient


def main():
    print("🧪 Teste Rápido F4 - Classificador PF/PJ")
    print("=" * 50)
    
    # 1. Carregar dados mock
    print("\n1️⃣ Carregando dados mock...")
    client = MockPluggyClient()
    response = client.get_transactions("acc_001")
    df = pl.DataFrame(response["results"])
    print(f"   ✅ {len(df)} transações carregadas")
    
    # 2. Executar pipeline
    print("\n2️⃣ Executando pipeline ETL...")
    try:
        processed_df = run_etl_pipeline(
            transactions_df=df,
            user_id="test_user",
            account_id="acc_001"
        )
        print(f"   ✅ Pipeline executado com sucesso")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return 1
    
    # 3. Verificar classificação
    print("\n3️⃣ Verificando classificação PF/PJ...")
    
    if "pf_pj_label" not in processed_df.columns:
        print("   ❌ FALHOU: Coluna pf_pj_label não encontrada")
        return 1
    
    pf_count = len(processed_df.filter(pl.col("pf_pj_label") == "PF"))
    pj_count = len(processed_df.filter(pl.col("pf_pj_label") == "PJ"))
    uncertain = len(processed_df.filter(pl.col("pf_pj_label") == "UNCERTAIN"))
    
    print(f"   ✅ Classificação funcionando!")
    print(f"      PF: {pf_count}")
    print(f"      PJ: {pj_count}")
    print(f"      UNCERTAIN: {uncertain}")
    
    # 4. Mostrar amostra
    print("\n4️⃣ Amostra de resultados:")
    print("\nPF (Pessoal):")
    pf_sample = processed_df.filter(pl.col("pf_pj_label") == "PF").head(3)
    for row in pf_sample.iter_rows(named=True):
        print(f"   - {row['description'][:40]}")
    
    print("\nPJ (Empresarial):")
    pj_sample = processed_df.filter(pl.col("pf_pj_label") == "PJ").head(3)
    for row in pj_sample.iter_rows(named=True):
        print(f"   - {row['description'][:40]}")
    
    # 5. Resultado
    print("\n" + "=" * 50)
    print("✅ TESTE PASSOU! Classificador PF/PJ funcionando!")
    print("=" * 50)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())