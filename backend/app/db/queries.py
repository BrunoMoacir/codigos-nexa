# app/db/queries.py

import duckdb
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "finance.duckdb"

def get_connection():
    """Retorna conexão com DuckDB"""
    return duckdb.connect(DB_PATH)

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
        # 1. Inserir na tabela de histórico (context_overrides)
        
        # Remove override anterior se houver
        con.execute("""
            DELETE FROM context_overrides 
            WHERE transaction_id = ? AND user_id = ?
        """, [transaction_id, user_id])
        
        # Inserir novo
        con.execute("""
            INSERT INTO context_overrides (
                id, transaction_id, user_id, original_context, 
                corrected_context, reason, created_at
            ) VALUES (
                uuid(), ?, ?, ?, ?, ?, current_timestamp
            )
        """, [transaction_id, user_id, original_context, corrected_context, reason])
        
        # 2. Atualizar a transação na tabela principal (transactions_clean)
        con.execute("""
            UPDATE transactions_clean
            SET 
                context_type = ?,
                context_override_by_user = TRUE,
                context_confidence = 1.0
            WHERE transaction_id = ?
        """, [corrected_context, transaction_id])
        
        logger.info(f"Override salvo para txn {transaction_id}: {corrected_context}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar override: {e}")
        return False
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
