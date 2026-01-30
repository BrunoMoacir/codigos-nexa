# app/etl/bank_strategy/strategies/inter.py

import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import BankTier, DataStatus


class InterStrategy(BankStrategy):
    """
    Estratégia TIER_2 para Banco Inter.
    
    CARACTERÍSTICAS:
        - Formato US (1,500.00)
        - Datas SQL (YYYY-MM-DD HH:MM:SS)
        - Qualidade boa
    """
    
    tier = BankTier.TIER_2
    
    def __init__(self):
        super().__init__(bank_id="inter")
    
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Inter.
        
        1. Converte transaction_date (SQL format)
        2. Normaliza merchant (trim + lowercase)
        """
        # 1. Transaction date (SQL: YYYY-MM-DD HH:MM:SS)
        df = df.with_columns(
            pl.col("transaction_date")
            .str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S", strict=False)
            .fill_null(pl.col("transaction_date"))
        )
        
        # 2. Merchant (trim + lowercase)
        if "merchant" in df.columns:
            df = df.with_columns(
                pl.col("merchant")
                .str.strip_chars()
                .str.to_lowercase()
                .alias("merchant")
            )
        
        return df
    
    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Inter: qualidade boa se campos fundamentais presentes.
        
        TRUSTED se:
            - transaction_date válida
            - balance presente
        
        DEGRADED se:
            - balance ausente mas data válida
        
        UNTRUSTED se:
            - transaction_date inválida
        """
        # Verifica datas inválidas
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED
        
        # Verifica balance (Inter sempre envia)
        if "balance" not in df.columns or df.filter(pl.col("balance").is_null()).height > 0:
            return DataStatus.DEGRADED
        
        return DataStatus.TRUSTED