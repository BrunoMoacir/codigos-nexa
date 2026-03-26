import duckdb
import os
import logging
import shutil

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from pathlib import Path
_BACKEND_DIR = Path(__file__).parent.parent.parent
DB_PATH = str(_BACKEND_DIR / "finance.duckdb")
DATA_DB_PATH = str(_BACKEND_DIR / "data" / "transactions.duckdb")
MIGRATIONS_DIR = str(_BACKEND_DIR / "app" / "db" / "migrations")

def init_db():
    """
    Inicializa o banco de dados principal a partir do seed data se necessário.
    Usa ATTACH para copiar dados de forma robusta.
    """
    logger.info(f"🔨 Inicializando banco de dados...")
    con = duckdb.connect(DB_PATH)
    
    try:
        # Verificar tabelas existentes
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        logger.info(f"📊 Tabelas antes da init: {tables}")
        
        # Se transactions não existe, importar do data_db
        if 'transactions' not in tables:
            if os.path.exists(DATA_DB_PATH):
                logger.info(f"📦 Importando transactions de {DATA_DB_PATH}...")
                con.execute(f"ATTACH '{DATA_DB_PATH}' AS data_db (READ_ONLY)")
                con.execute("CREATE TABLE transactions AS SELECT * FROM data_db.transactions")
                con.execute("DETACH data_db")
                logger.info("✅ Tabela transactions importada com sucesso!")
            else:
                logger.warning(f"⚠️  Seed DB {DATA_DB_PATH} não encontrado. Não foi possível importar transactions.")

        # Atualizar lista de tabelas
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        
        # Se transactions_clean não existe, criar a partir de transactions (ou vazia se transactions não existir)
        if 'transactions_clean' not in tables:
            if 'transactions' in tables:
                logger.info("🔨 Criando transactions_clean a partir de transactions...")
                con.execute("CREATE TABLE transactions_clean AS SELECT * FROM transactions")
            else:
                logger.info("🔨 Criando transactions_clean vazia (schema mínimo)...")
                # Se não temos dados, não podemos criar AS SELECT. 
                # O ideal seria ter o schema definido. 
                # Vamos tentar criar vazia se for o caso, mas as migrations vão assumir schema.
                # Se transaction existe, ok. Se não, estamos num estado ruim.
    
    except Exception as e:
        logger.error(f"❌ Erro na inicialização do DB: {e}")
    finally:
        con.close()

def apply_migrations():
    """
    Aplica arquivos .sql de migrations no DuckDB local.
    Adapta sintaxe Postgres -> DuckDB on-the-fly.
    """
    
    # 1. Inicializar banco
    init_db()
    
    # 2. Conectar ao banco
    logger.info(f"🔌 Conectando ao banco: {DB_PATH}")
    con = duckdb.connect(DB_PATH)
    
    # 3. Listar arquivos SQL
    try:
        migration_files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql')])
    except FileNotFoundError:
        logger.error(f"❌ Diretório de migrations não encontrado: {MIGRATIONS_DIR}")
        return

    logger.info(f"📂 Encontradas {len(migration_files)} migrations")

    for sql_file in migration_files:
        logger.info(f"🚀 Aplicando: {sql_file}")
        file_path = os.path.join(MIGRATIONS_DIR, sql_file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # 4. Adaptação de Sintaxe (Postgres -> DuckDB)
        fixed_sql = sql_content.replace("gen_random_uuid()", "uuid()")
        
        statements = [s.strip() for s in fixed_sql.split(';') if s.strip()]
        
        for stmt in statements:
            if stmt.startswith('--'):
                continue
                
            try:
                con.execute(stmt)
            except duckdb.CatalogException as e:
                if "already exists" in str(e) or "already has a column" in str(e):
                    logger.warning(f"   ⚠️  Alerta: {e}")
                else:
                    logger.error(f"   ❌ Erro ao rodar statement: {stmt[:50]}...")
                    logger.error(f"   ❌ Motivo: {e}")
            except Exception as e:
                logger.error(f"   ❌ Erro inesperado: {e}")
                
    # 5. Verificação Final e Logs detalhados
    try:
        if 'transactions_clean' in [t[0] for t in con.execute("SHOW TABLES").fetchall()]:
             columns = con.execute("DESCRIBE transactions_clean").fetchall()
             col_names = [c[0] for c in columns]
             logger.info(f"📋 Colunas em transactions_clean: {col_names}")
             
             required = ['context_type', 'context_confidence', 'context_override_by_user']
             present = [c for c in required if c in col_names]
             if len(present) == 3:
                 logger.info("✅ Sucesso: transactions_clean tem todas as colunas novas!")
             else:
                 logger.warning(f"⚠️  Faltam colunas: {[c for c in required if c not in col_names]}")
        else:
            logger.error("❌ Erro Crítico: transactions_clean não existe após init e migrations!")

        if 'context_overrides' in [t[0] for t in con.execute("SHOW TABLES").fetchall()]:
             logger.info("✅ Sucesso: Tabela context_overrides existe!")
        else:
             logger.error("❌ Erro Crítico: context_overrides não foi criada!")
            
    except Exception as e:
         logger.error(f"❌ Erro na verificação: {e}")

    con.close()
    logger.info("🏁 Script finalizado.")

if __name__ == "__main__":
    apply_migrations()
