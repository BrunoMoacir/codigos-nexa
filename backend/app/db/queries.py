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
    """
    Retorna conexão com DuckDB usando caminho absoluto.

    ⚠️  SINGLE-WRITER: DuckDB embarcado não suporta múltiplos escritores
    simultâneos. Este módulo pressupõe execução single-process (FastAPI com
    1 worker ou Celery com concurrency=1). Em ambiente multi-worker, proteja
    chamadas de escrita com um threading.Lock externo ou migre para DuckDB
    server mode / outro banco.
    """
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
        logger.error(f"Erro ao salvar override: {e}")
        try:
            con.execute("ROLLBACK")
        except Exception as rb_err:
            logger.error(f"Falha no ROLLBACK (conexão corrompida?): {rb_err}")
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
                pj_subcategory           VARCHAR,
                processed_at             TIMESTAMP DEFAULT current_timestamp
            )
        """)
        # Adiciona coluna em tabelas existentes criadas antes dessa versão
        try:
            con.execute("ALTER TABLE transactions_clean ADD COLUMN IF NOT EXISTS pj_subcategory VARCHAR")
        except Exception:
            pass  # coluna ja existe

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
            "context_confidence", "context_override_by_user", "pj_subcategory",
        ]
        cols_to_save = [c for c in schema_cols if c in df.columns]
        df_to_save = df.select(cols_to_save)

        # Registrar DataFrame como view temporária e fazer upsert atômico
        con.register("_txn_batch", df_to_save.to_arrow())
        con.execute("BEGIN")
        try:
            con.execute(f"""
                INSERT OR REPLACE INTO transactions_clean ({', '.join(cols_to_save)})
                SELECT {', '.join(cols_to_save)} FROM _txn_batch
            """)
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception as rb_err:
                logger.error(f"Falha no ROLLBACK de transactions_clean: {rb_err}")
            raise
        finally:
            con.unregister("_txn_batch")

        rows = len(df_to_save)
        logger.info(f"transactions_clean: {rows} linhas salvas para user {user_id}")
        return rows

    except Exception as e:
        logger.error(f"Erro ao salvar transactions_clean: {e}")
        return 0
    finally:
        con.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MX.1 — Health Score History
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_health_score_history_table(con) -> None:
    """Cria a tabela health_score_history se não existir."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS health_score_history (
            user_id      VARCHAR NOT NULL,
            date         VARCHAR NOT NULL,
            health_score INTEGER NOT NULL,
            savings_rate DOUBLE,
            profile_type VARCHAR,
            safe_to_spend DOUBLE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, date)
        )
    """)


def save_health_score_snapshot(
    user_id: str,
    health_score: int,
    savings_rate: float,
    profile_type: str,
    safe_to_spend: Optional[float] = None,
    date: Optional[str] = None,
) -> bool:
    """
    Persiste um snapshot do health_score para o mês corrente (ou date informado).

    Args:
        user_id: ID do usuário.
        health_score: Score 0-100 calculado pelo UserProfileAnalyzer.
        savings_rate: Taxa de poupança (%).
        profile_type: CONSERVADOR | EQUILIBRADO | GASTADOR.
        safe_to_spend: Margem diária segura (opcional).
        date: Mês no formato 'YYYY-MM'. Padrão: mês atual.

    Returns:
        True se salvou com sucesso.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m")

    # Garantir formato 'YYYY-MM' zero-padded para ordenação lexicográfica correta.
    # Ex: '2026-3' → '2026-03'. Evita quebra silenciosa de ORDER BY date DESC.
    try:
        from datetime import datetime as _dt
        date = _dt.strptime(date, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise ValueError(f"Parâmetro 'date' deve estar no formato 'YYYY-MM', recebido: {date!r}")

    con = get_connection()
    try:
        _ensure_health_score_history_table(con)

        # INSERT OR REPLACE: atualiza se já existir registro para o mês
        con.execute("""
            INSERT OR REPLACE INTO health_score_history
                (user_id, date, health_score, savings_rate, profile_type, safe_to_spend, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NOW())
        """, [user_id, date, health_score, savings_rate, profile_type, safe_to_spend])

        logger.info(f"health_score_history: snapshot salvo para user={user_id} date={date} score={health_score}")
        return True

    except Exception as e:
        logger.error(f"Erro ao salvar health_score_history: {e}")
        return False
    finally:
        con.close()


def get_health_score_history(
    user_id: str,
    months: int = 6,
) -> List[Dict[str, Any]]:
    """
    Retorna histórico mensal do health_score de um usuário.

    Args:
        user_id: ID do usuário.
        months: Quantos meses de histórico retornar (padrão: 6).

    Returns:
        Lista de dicts com campos: date, health_score, savings_rate, profile_type, safe_to_spend.
        Ordenado do mais antigo para o mais recente.
    """
    con = get_connection()
    try:
        _ensure_health_score_history_table(con)

        rows = con.execute("""
            SELECT date, health_score, savings_rate, profile_type, safe_to_spend
            FROM health_score_history
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, [user_id, months]).fetchall()

        # Retornar do mais antigo ao mais recente (para gráfico de linha)
        history = [
            {
                "date": row[0],
                "health_score": row[1],
                "savings_rate": row[2],
                "profile_type": row[3],
                "safe_to_spend": row[4],
            }
            for row in reversed(rows)
        ]
        return history

    except Exception as e:
        logger.error(f"Erro ao buscar health_score_history: {e}")
        return []
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
