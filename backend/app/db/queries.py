# app/db/queries.py

import duckdb
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Caminho absoluto: <repo>/backend/finance.duckdb
_DB_PATH = str(Path(__file__).parent.parent.parent / "finance.duckdb")


def get_connection():
    """Retorna conexão com DuckDB usando caminho absoluto."""
    return duckdb.connect(_DB_PATH)

def get_context_overrides(user_id: str) -> List[Dict[str, Any]]:
    """
    Busca todos os overrides ativos de um usuário.
    Retorna lista de dicts.
    """
    con = get_connection()
    try:
        # Verificar se tabela existe (segurança)
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        if 'context_overrides' not in tables:
            logger.warning("Tabela context_overrides não encontrada.")
            return []

        query = """
            SELECT 
                transaction_id, 
                original_context, 
                corrected_context, 
                reason,
                created_at
            FROM context_overrides 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """
        
        # DuckDB retorna lista de tuplas por padrão.
        # Vamos converter p/ lista de dicts para facilitar uso.
        # .df() retorna pandas, .pl() polars, .fetchall() tuplas.
        # .arrow() -> to_pylist() é eficiente.
        
        result = con.execute(query, [user_id]).fetchall()
        
        overrides = []
        for row in result:
            overrides.append({
                "transaction_id": row[0],
                "original_context": row[1],
                "corrected_context": row[2],
                "reason": row[3],
                "created_at": row[4]
            })
            
        return overrides
        
    except Exception as e:
        logger.error(f"Erro ao buscar overrides: {e}")
        return []
    finally:
        con.close()

def save_context_override(
    user_id: str,
    transaction_id: str,
    corrected_context: str,
    original_context: Optional[str] = None,
    reason: Optional[str] = None
) -> bool:
    """
    Salva ou atualiza um override de contexto.
    Também atualiza a tabela transactions_clean para refletir a mudança imediatamente.
    """
    con = get_connection()
    try:
        con.execute("BEGIN")

        # 1. Upsert em context_overrides (DELETE+INSERT dentro da transação)
        con.execute("""
            DELETE FROM context_overrides
            WHERE transaction_id = ? AND user_id = ?
        """, [transaction_id, user_id])

        con.execute("""
            INSERT INTO context_overrides (
                id, transaction_id, user_id, original_context,
                corrected_context, reason, created_at
            ) VALUES (
                uuid(), ?, ?, ?, ?, ?, current_timestamp
            )
        """, [transaction_id, user_id, original_context, corrected_context, reason])

        # 2. Refletir o override em transactions_clean
        con.execute("""
            UPDATE transactions_clean
            SET
                context_type = ?,
                context_override_by_user = TRUE,
                context_confidence = 1.0
            WHERE transaction_id = ?
        """, [corrected_context, transaction_id])

        con.execute("COMMIT")
        logger.info(f"Override salvo para txn {transaction_id}: {corrected_context}")
        return True

    except Exception as e:
        con.execute("ROLLBACK")
        logger.error(f"Erro ao salvar override: {e}")
        return False
    finally:
        con.close()

def save_transactions_clean(
    df,
    user_id: str,
    account_id: Optional[str] = None,
) -> int:
    """
    Persiste o DataFrame processado em transactions_clean.
    Cria a tabela se não existir. Upsert por transaction_id (idempotente).

    Mapeia colunas do ETL para o schema da tabela:
        predicted_category  → category
        pf_pj_label         → context_type
        pf_pj_confidence    → context_confidence

    Returns:
        Número de linhas inseridas/atualizadas.
    """
    import polars as pl

    con = get_connection()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS transactions_clean (
                transaction_id           VARCHAR PRIMARY KEY,
                user_id                  VARCHAR NOT NULL,
                account_id               VARCHAR,
                description              VARCHAR,
                amount                   DOUBLE,
                date                     DATE,
                transaction_type         VARCHAR,
                category                 VARCHAR,
                is_recurring             BOOLEAN DEFAULT FALSE,
                is_installment           BOOLEAN DEFAULT FALSE,
                context_type             VARCHAR,
                context_confidence       DOUBLE,
                context_override_by_user BOOLEAN DEFAULT FALSE,
                processed_at             TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # Adicionar colunas obrigatórias ausentes
        if "user_id" not in df.columns:
            df = df.with_columns(pl.lit(user_id).alias("user_id"))
        if "account_id" not in df.columns:
            df = df.with_columns(pl.lit(account_id).alias("account_id"))

        # Renomear colunas do ETL para o schema da tabela
        rename_map = {
            "predicted_category": "category",
            "pf_pj_label": "context_type",
            "pf_pj_confidence": "context_confidence",
        }
        for old_name, new_name in rename_map.items():
            if old_name in df.columns and new_name not in df.columns:
                df = df.rename({old_name: new_name})

        # Selecionar apenas colunas presentes no schema
        schema_cols = [
            "transaction_id", "user_id", "account_id", "description",
            "amount", "date", "transaction_type", "category",
            "is_recurring", "is_installment", "context_type",
            "context_confidence", "context_override_by_user",
        ]
        cols_to_save = [c for c in schema_cols if c in df.columns]
        df_to_save = df.select(cols_to_save)

        # Registrar DataFrame como view temporária e fazer upsert
        con.register("_txn_batch", df_to_save.to_arrow())
        con.execute(f"""
            INSERT OR REPLACE INTO transactions_clean ({', '.join(cols_to_save)})
            SELECT {', '.join(cols_to_save)} FROM _txn_batch
        """)
        con.unregister("_txn_batch")

        rows = len(df_to_save)
        logger.info(f"transactions_clean: {rows} linhas salvas para user {user_id}")
        return rows

    except Exception as e:
        logger.error(f"Erro ao salvar transactions_clean: {e}")
        return 0
    finally:
        con.close()


def get_override_stats(user_id: str) -> Dict[str, int]:
    """
    Retorna estatísticas de overrides do usuário.
    """
    con = get_connection()
    try:
        query = """
            SELECT corrected_context, COUNT(*) 
            FROM context_overrides 
            WHERE user_id = ? 
            GROUP BY corrected_context
        """
        rows = con.execute(query, [user_id]).fetchall()
        
        stats = {row[0]: row[1] for row in rows}
        return stats
        
    except Exception as e:
        logger.error(f"Erro ao buscar stats: {e}")
        return {}
    finally:
        con.close()
