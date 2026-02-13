"""
test_pipeline_integration.py - Testa integração do PF/PJ Classifier no pipeline
"""

import sys
import os

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.runner import NexaRunner

def test_pipeline():
    """Testa pipeline completo com PF/PJ classifier"""
    print("🧪 TESTANDO PIPELINE COM PF/PJ CLASSIFIER")
    print("=" * 50)

    try:
        # Inicializa runner
        runner = NexaRunner()

        # Executa pipeline
        result = runner.run(horizon_days=7)  # Menos dias para teste rápido

        if result['status'] == 'success':
            print("✅ Pipeline executado com sucesso!")

            # Verifica se PF/PJ foi adicionado
            pf_pj_df = result['transactions']['pf_pj_classified_df']
            print(f"📊 Transações classificadas: {len(pf_pj_df)}")

            # Conta PF vs PJ
            pf_count = len(pf_pj_df.filter(pf_pj_df['pf_pj_label'] == 'PF'))
            pj_count = len(pf_pj_df.filter(pf_pj_df['pf_pj_label'] == 'PJ'))
            uncertain_count = len(pf_pj_df.filter(pf_pj_df['pf_pj_label'] == 'UNCERTAIN'))

            print(f"   PF: {pf_count} transações")
            print(f"   PJ: {pj_count} transações")
            print(f"   UNCERTAIN: {uncertain_count} transações")

            # Mostra amostra
            print("\n📋 Amostra de classificações:")
            sample = pf_pj_df.head(5).select(['description', 'amount', 'category', 'pf_pj_label'])
            for row in sample.iter_rows():
                print(f"   {row[3]} | R$ {row[1]:.2f} | {row[0][:40]}... | {row[2]}")

        else:
            print(f"❌ Erro no pipeline: {result.get('error', 'Unknown')}")

    except Exception as e:
        print(f"❌ Exceção durante teste: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pipeline()