"""
app/etl/ingestor.py - Transforma JSON → DataFrame limpo (Polars)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
import polars as pl

from app.core.schemas.transaction import TransactionWebhook
from app.forecast.etl.bank_strategy import get_bank_strategy

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

    def __init__(self):
        """
        Inicializa o TransactionIngestor.
        (Removida a dependência legacy do DuckDB)
        """
        self.logger = logging.getLogger(__name__)

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

        # 2. Normalização de texto
        df = self._normalize_texts(df)

        # 3. BankStrategy
        df = self._apply_bank_strategies(df)

        # 4. Conversão de tipos
        df = self._convert_types(df)

        # 5. Enriquecimento
        df = self._enrich_columns(df)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        metrics = QualityMetrics(
            total_records=len(transactions),
            duplicates_removed=0, # Legacy
            records_after_dedup=len(df),
            quality_score=1.0, # Assumindo 100% de qualidade pré-validação
            processing_time_ms=processing_time,
            trusted_count=df.filter(pl.col("data_status") == "TRUSTED").height if "data_status" in df.columns else len(df),
            degraded_count=df.filter(pl.col("data_status") == "DEGRADED").height if "data_status" in df.columns else 0,
            untrusted_count=df.filter(pl.col("data_status") == "UNTRUSTED").height if "data_status" in df.columns else 0,
            inserted_rows=0 # Load agora é feito no postgres no pipeline principal
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
    # PASSO 3 — BANK STRATEGY
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
    # PASSO 4 — TIPOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _convert_types(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns(pl.col("amount").cast(pl.Float64))
        if "balance" in df.columns:
            df = df.with_columns(pl.col("balance").cast(pl.Float64))
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5 — ENRIQUECIMENTO
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
