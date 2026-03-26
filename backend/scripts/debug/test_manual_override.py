import requests
import json
import logging
import duckdb
from time import sleep

# Configuração
BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "user_123"
TRANSACTION_ID = "txn_test_001"
DB_PATH = "finance.duckdb"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Tester")

def ensure_schema_and_data():
    """
    Garante que colunas existem e cria transação de teste.
    """
    try:
        con = duckdb.connect(DB_PATH)
        
        # 1. Verificar Colunas e Adicionar se Faltar (Patching)
        logger.info("🛠️  Verificando schema...")
        cols_info = con.execute("DESCRIBE transactions_clean").fetchall()
        col_names = [c[0] for c in cols_info]
        
        needed_cols = {
            'context_type': 'VARCHAR(20)',
            'context_confidence': 'FLOAT',
            'context_override_by_user': 'BOOLEAN DEFAULT FALSE'
        }
        
        for col, type_def in needed_cols.items():
            if col not in col_names:
                logger.warning(f"⚠️  Coluna {col} faltando. Adicionando...")
                try:
                    con.execute(f"ALTER TABLE transactions_clean ADD COLUMN {col} {type_def}")
                except Exception as e:
                    logger.error(f"   Erro ao adicionar coluna: {e}")

        # 2. Inserir Transação de Teste
        logger.info("🛠️  Verificando transação de teste...")
        exists = con.execute("SELECT 1 FROM transactions_clean WHERE transaction_id = ?", [TRANSACTION_ID]).fetchone()
        
        if not exists:
            logger.info("🛠️  Criando transação de teste...")
            
            # Montar INSERT dinâmico com colunas disponíveis
            insert_cols = ['transaction_id', 'amount', 'description', 'merchant', 'transaction_date', 'data_status']
            # Se user_id existir, usar. Se não, ignorar.
            if 'user_id' in col_names:
                insert_cols.append('user_id')
                vals = [TRANSACTION_ID, -50.0, 'TESTE MANUAL', 'Teste Merchant', '2025-01-01', 'POSTED', USER_ID]
            else:
                vals = [TRANSACTION_ID, -50.0, 'TESTE MANUAL', 'Teste Merchant', '2025-01-01', 'POSTED']
            
            placeholders = ', '.join(['?' for _ in vals])
            col_str = ', '.join(insert_cols)
            
            sql = f"INSERT INTO transactions_clean ({col_str}) VALUES ({placeholders})"
            con.execute(sql, vals)
            logger.info("✅ Transação de teste criada.")
        else:
            logger.info("ℹ️  Transação de teste já existe.")
            
        con.close()
    except Exception as e:
        logger.error(f"❌ Erro ao preparar banco: {e}")

def test_override_flow():
    """
    Testa o fluxo completo de Override de Contexto PF/PJ.
    """
    logger.info("🚀 Iniciando Teste Manual: Context Override API")
    
    # 0. Preparar Banco
    ensure_schema_and_data()
    
    # 1. Verificar Overrides Originais
    logger.info("\n[1] GET /overrides - Verificando estado inicial...")
    try:
        resp = requests.get(f"{BASE_URL}/context/overrides?user_id={USER_ID}")
        if resp.status_code == 200:
            logger.info(f"✅ Sucesso: {len(resp.json())} overrides encontrados.")
        else:
            logger.error(f"❌ Falha: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"❌ Erro de conexão: {e}")
        return

    # 2. Criar um Override (Corrigir PJ -> PF)
    logger.info(f"\n[2] POST /context/override - Criando correção para {TRANSACTION_ID}...")
    payload = {
        "transaction_id": TRANSACTION_ID,
        "corrected_context": "PF",
        "reason": "Almoço de domingo em família"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/context/override?user_id={USER_ID}", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            logger.info("✅ Override criado com sucesso!")
            logger.info(f"   Original: {data.get('original_context')}")
            logger.info(f"   Corrigido: {data.get('corrected_context')}")
            logger.info(f"   Mensagem: {data.get('message')}")
        else:
            logger.error(f"❌ Falha ao criar override: {resp.status_code} - {resp.text}")
            return
    except Exception as e:
         logger.error(f"❌ Erro ao enviar POST: {e}")
         return

    # 3. Verificar se foi salvo
    logger.info("\n[3] GET /overrides - Confirmando persistência...")
    sleep(1) 
    try:
        resp = requests.get(f"{BASE_URL}/context/overrides?user_id={USER_ID}")
        overrides = resp.json()
        
        found = False
        for o in overrides:
            if o['transaction_id'] == TRANSACTION_ID and o['corrected_context'] == 'PF':
                found = True
                break
        
        if found:
            logger.info(f"✅ Sucesso: Override para {TRANSACTION_ID} encontrado na lista!")
        else:
            logger.error(f"❌ Erro: Override não encontrado na lista retornada.")
            logger.info(f"   Lista completa: {overrides}")

    except Exception as e:
        logger.error(f"❌ Erro no GET: {e}")

    # 4. Verificar Estatísticas
    logger.info("\n[4] GET /overrides/stats - Verificando métricas...")
    try:
        resp = requests.get(f"{BASE_URL}/context/overrides/stats?user_id={USER_ID}")
        if resp.status_code == 200:
            stats = resp.json()
            logger.info(f"✅ Stats: {json.dumps(stats, indent=2)}")
        else:
            logger.warning(f"⚠️  Stats endpoint retornou {resp.status_code}")

    except Exception as e:
        logger.error(f"❌ Erro no Stats: {e}")

    logger.info("\n🏁 Teste Manual Finalizado.")

if __name__ == "__main__":
    print(f"URL Base: {BASE_URL}")
    print("Certifique-se de que o servidor backend está rodando (uvicorn app.main:app)!")
    # input("Pressione Enter para começar...")
    test_override_flow()
