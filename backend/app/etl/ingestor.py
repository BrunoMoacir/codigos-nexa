"""
app/etl/ingestor.py - Transforma JSON → DataFrame limpo (Polars)
e persiste no DuckDB com idempotência cross-lote
"""

import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from pathlib import Path

import polars as pl
import duckdb

from app.schemas.transaction import TransactionWebhook
from app.etl.bank_strategy import get_bank_strategy

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: MÉTRICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class QualityMetrics:
    total_records: int
    duplicates_removed: int
    records_after_dedup: int
    quality_score: float
    processing_time_ms: float

    trusted_count: int = 0
    degraded_count: int = 0
    untrusted_count: int = 0
    inserted_rows: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INGESTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TransactionIngestor:

    def __init__(self, db_path: str = None):
        """
        Inicializa o TransactionIngestor.
    
        Args:
            db_path: Caminho customizado para o banco DuckDB.
                    Se None, usa: <project_root>/data/transactions.duckdb
        """
        self.logger = logging.getLogger(__name__)
    
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Configurar caminho do banco
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if db_path is None:
            # Caminho padrão: <project_root>/data/transactions.duckdb
            project_root = Path(__file__).parent.parent.parent.parent
            self.db_path = str(project_root / "data" / "transactions.duckdb")
        else:
            self.db_path = db_path
    
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Criar diretório se não existir
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
        self.logger.info(f"DuckDB path: {self.db_path}")
    
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Inicializar banco
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self._init_db()


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INIT DB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _init_db(self):
        with duckdb.connect(self.db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT,
                    institution_id TEXT,
                    account_id TEXT,
                    description TEXT,
                    merchant TEXT,
                    amount DOUBLE,
                    balance DOUBLE,
                    currency TEXT,
                    transaction_date TIMESTAMP,
                    fetched_at TIMESTAMP,
                    dedup_hash TEXT UNIQUE,
                    data_status TEXT,
                    month INTEGER,
                    day_of_week INTEGER,
                    transaction_type TEXT
                )
            """)

        logger.info("DuckDB inicializado", extra={"db_path": self.db_path})

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PROCESS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def process(
        self,
        transactions: list[TransactionWebhook]
    ) -> tuple[pl.DataFrame, QualityMetrics]:

        if not transactions:
            raise ValueError("Lista de transações vazia")

        start_time = datetime.now()

        # 1. JSON → DataFrame
        df = self._to_dataframe(transactions)

        # 2. Normalização de texto (ANTES do hash)
        df = self._normalize_texts(df)

        # 3. Criar dedup_hash
        df = self._create_dedup_hash(df)

        # 4. Deduplicação intra-lote
        df, duplicates_removed = self._deduplicate(df)

        # 5. BankStrategy
        df = self._apply_bank_strategies(df)

        # 6. Conversão de tipos
        df = self._convert_types(df)

        # 7. Enriquecimento
        df = self._enrich_columns(df)

        # 8. Load no DuckDB (idempotente)
        inserted_rows = self._load_duckdb(df)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        metrics = QualityMetrics(
            total_records=len(transactions),
            duplicates_removed=duplicates_removed,
            records_after_dedup=len(df),
            quality_score=len(df) / len(transactions),
            processing_time_ms=processing_time,
            trusted_count=df.filter(pl.col("data_status") == "TRUSTED").height,
            degraded_count=df.filter(pl.col("data_status") == "DEGRADED").height,
            untrusted_count=df.filter(pl.col("data_status") == "UNTRUSTED").height,
            inserted_rows=inserted_rows
        )

        return df, metrics

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _to_dataframe(self, transactions: list[TransactionWebhook]) -> pl.DataFrame:
        return pl.DataFrame([tx.model_dump() for tx in transactions])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2 — NORMALIZAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _normalize_texts(self, df: pl.DataFrame) -> pl.DataFrame:
        for col in ["description", "merchant"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col)
                    .cast(pl.String)
                    .fill_null("")
                    .str.strip_chars()
                    .str.to_lowercase()
                    .alias(col)
                )
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3 — DEDUP HASH
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _create_dedup_hash(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns(
            pl.col("description")
            .str.replace_all(r"\s+", " ")
            .str.split(" ")
            .list.slice(0, 2)          # 👈 usa só as 2 primeiras palavras
            .list.join(" ")
            .alias("dedup_desc")
        )

        return df.with_columns(
            pl.concat_str(
                [
                    pl.col("account_id"),
                    pl.col("amount").cast(pl.Utf8),
                    pl.col("transaction_date").cast(pl.Utf8),
                    pl.col("dedup_desc")
                ],
                separator="|"
            )
            .map_elements(lambda x: hashlib.sha256(x.encode()).hexdigest())
            .alias("dedup_hash")
    ).drop("dedup_desc")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4 — DEDUPLICAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _deduplicate(self, df: pl.DataFrame):
        before = df.height
        df = df.unique(subset=["dedup_hash"], keep="first")
        return df, before - df.height

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5 — BANK STRATEGY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _apply_bank_strategies(self, df: pl.DataFrame) -> pl.DataFrame:
        banks = df.select("institution_id").unique().to_series().to_list()
        processed = []

        for bank_id in banks:
            bank_df = df.filter(pl.col("institution_id") == bank_id)
            try:
                strategy = get_bank_strategy(bank_id)
                bank_df = strategy.normalize(bank_df)
                status = strategy.evaluate_quality(bank_df)
                bank_df = bank_df.with_columns(
                    pl.lit(status.value).alias("data_status")
                )
            except Exception:
                bank_df = bank_df.with_columns(
                    pl.lit("UNTRUSTED").alias("data_status")
                )

            processed.append(bank_df)

        return pl.concat(processed, how="diagonal_relaxed")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 6 — TIPOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _convert_types(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns(pl.col("amount").cast(pl.Float64))
        if "balance" in df.columns:
            df = df.with_columns(pl.col("balance").cast(pl.Float64))
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7 — ENRIQUECIMENTO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns([
            pl.col("transaction_date").dt.month().alias("month"),
            pl.col("transaction_date").dt.weekday().alias("day_of_week"),
            pl.when(pl.col("amount") < 0)
              .then(pl.lit("DEBIT"))
              .otherwise(pl.lit("CREDIT"))
              .alias("transaction_type")
        ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 8 — LOAD DUCKDB (IDEMPOTENTE)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _load_duckdb(self, df: pl.DataFrame) -> int:
        with duckdb.connect(self.db_path) as con:
            con.register("df_view", df.to_pandas())

            result = con.execute("""
                INSERT OR IGNORE INTO transactions
                SELECT
                    transaction_id,
                    institution_id,
                    account_id,
                    description,
                    merchant,
                    amount,
                    balance,
                    currency,
                    transaction_date,
                    fetched_at,
                    dedup_hash,
                    data_status,
                    month,
                    day_of_week,
                    transaction_type
                FROM df_view
            """)

            return result.rowcount
