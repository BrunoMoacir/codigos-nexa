import duckdb
import polars as pl
from pathlib import Path


class DuckDBLoader:
    """
    Responsável por persistir dados no DuckDB
    com idempotência cross-lote
    """

    def __init__(self, db_path: str = "data/etl.duckdb"):
        self.db_path = db_path
        Path("data").mkdir(exist_ok=True)

    def connect(self):
        """
        Abre conexão com o DuckDB
        """
        return duckdb.connect(self.db_path)

    def create_table_if_not_exists(self, con):
        """
        Cria tabela de transações com chave idempotente
        """
        con.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT,
                item_id TEXT,
                institution_id TEXT,
                amount DOUBLE,
                description TEXT,
                transaction_date TIMESTAMP,
                fetched_at TIMESTAMP,
                transaction_type TEXT,
                dedup_hash TEXT UNIQUE,
                data_status TEXT
            )
        """)

    def load(self, df: pl.DataFrame) -> int:
        """
        Insere dados no banco evitando duplicatas
        Retorna quantidade de registros inseridos
        """
        if df.is_empty():
            return 0

        con = self.connect()
        self.create_table_if_not_exists(con)

        # Polars → Arrow → DuckDB
        con.register("incoming_df", df.to_arrow())

        # INSERT idempotente
        result = con.execute("""
            INSERT INTO transactions
            SELECT
                transaction_id,
                item_id,
                institution_id,
                amount,
                description,
                transaction_date,
                fetched_at,
                transaction_type,
                dedup_hash,
                data_status
            FROM incoming_df
            ON CONFLICT(dedup_hash) DO NOTHING
        """).rowcount

        con.close()
        return result
