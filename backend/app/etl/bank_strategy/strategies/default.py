# app/etl/bank_strategy/strategies/default.py

import polars as pl

from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import BankTier, DataStatus


class DefaultStrategy(BankStrategy):
    """
    Estratégia padrão para bancos desconhecidos
    ou ainda não mapeados.
    """

    tier = BankTier.TIER_3  # conservador

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        # Nenhuma normalização específica
        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        # Se campos fundamentais existirem → DEGRADED
        required = {"transaction_id", "amount", "transaction_date"}

        missing = required - set(df.columns)

        if missing:
            return DataStatus.UNTRUSTED

        return DataStatus.DEGRADED
