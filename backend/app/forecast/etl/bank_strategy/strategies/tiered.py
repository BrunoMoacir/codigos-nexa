# app/etl/bank_strategy/strategies/tiered.py

import polars as pl

from app.core.schemas.enums import BankTier, DataStatus
from app.forecast.etl.bank_strategy.base import BankStrategy


class TieredStrategy(BankStrategy):
    """
    Strategy genérica parametrizada por tier — para bancos que o resolvedor
    de instituição reconhece mas que ainda não têm peculiaridade própria
    mapeada (Bradesco, Santander, C6, Caixa...).

    Antes, todos caíam na DefaultStrategy: teto DEGRADED e nenhuma
    normalização, mesmo quando o banco é de dados excelentes (C6, BTG).
    O conhecimento real por tier vem do enum BankTier, calibrado em produção.

    Quando um banco ganhar quirk próprio (como o sinal invertido do Itaú),
    promove-se a classe dedicada — o registry decide.
    """

    def __init__(self, bank_id: str, tier: BankTier):
        super().__init__(bank_id)
        self.tier = tier

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        # Normalização genérica segura: merchant trim + lowercase.
        # O trabalho pesado (chave canônica, qualidade por linha) é do
        # ingestor, comum a todos os bancos.
        if "merchant" in df.columns:
            df = df.with_columns(
                pl.col("merchant")
                .cast(pl.String)
                .str.strip_chars()
                .str.to_lowercase()
                .alias("merchant")
            )
        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Teto de confiança pelo tier do banco. Lacunas de linha são
        rebaixadas depois, no TransactionIngestor._apply_row_quality().
        """
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED

        if self.tier in (BankTier.TIER_1, BankTier.TIER_2):
            return DataStatus.TRUSTED

        # TIER_3 (legados problemáticos) e TIER_4 (instáveis): sempre com
        # ressalva — força o blend com Shadow Invoice.
        return DataStatus.DEGRADED
