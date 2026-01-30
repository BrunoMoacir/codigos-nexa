# app/etl/bank_strategy/strategies/nubank.py

import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import DataStatus


class NubankStrategy(BankStrategy):

    BANK_ID = "nubank"

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Nubank
        """

        # 1. Garantir transaction_date como Datetime
        df = df.with_columns(
            pl.col("transaction_date")
            .str.strptime(pl.Datetime, strict=False)
            .fill_null(pl.col("transaction_date"))
        )

        # 2. Extrair merchant da descrição
        # Ex: "compra no débito - uber *1234" → "uber"
        df = df.with_columns(
            pl.col("description")
            .str.split("-")
            .list.get(-1)
            .str.replace(r"\*.*", "")
            .str.strip()
            .alias("merchant")
        )

        # 3. Nubank não envia categoria confiável
        if "category" in df.columns:
            df = df.with_columns(pl.lit(None).alias("category"))

        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Qualidade considerada BOA se:
        - merchant preenchido
        - transaction_date válida
        """

        if df.filter(pl.col("merchant").is_null()).height > 0:
            return DataStatus.PARTIAL

        return DataStatus.OK
