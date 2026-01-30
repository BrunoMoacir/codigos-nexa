# app/etl/bank_strategy/strategies/itau.py

import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import DataStatus, BankTier


class ItauStrategy(BankStrategy):

    tier = BankTier.TIER_3

    BANK_ID = "itau"

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Itaú
        """

        # # 1. Converter transaction_date (string → datetime)
        # df = df.with_columns(
        #     pl.col("transaction_date")
        #     .str.strptime(pl.Datetime, format="%Y-%m-%d", strict=False)
        #     .fill_null(pl.col("transaction_date"))
        # )

        # 2. Normalizar merchant (CAIXA ALTA → lowercase)
        if "merchant" in df.columns:
            df = df.with_columns(
                pl.col("merchant")
                .str.to_lowercase()
                .str.strip()
                .alias("merchant")
            )

        # 3. Corrigir sinal do amount baseado no transaction_type
        if "transaction_type" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("transaction_type") == "DEBIT")
                .then(pl.col("amount") * -1)
                .otherwise(pl.col("amount"))
                .alias("amount")
            )

        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Qualidade considerada RUIM se:
        - datas inválidas
        """

        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.BAD

        return DataStatus.OK
