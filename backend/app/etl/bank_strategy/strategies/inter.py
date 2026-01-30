# app/etl/bank_strategy/strategies/inter.py

import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import BankTier, DataStatus


class InterStrategy(BankStrategy):
    """
    Estratégia TIER_2 para Banco Inter (Boa qualidade).
    
    CARACTERÍSTICAS:
        - Tier: TIER_2 (qualidade boa)
        - Formato: US (1,500.00)
        - Data: SQL format (YYYY-MM-DD HH:MM:SS)
        - Campos: Sempre completos
        - Campo especial: "value" em vez de "amount"
    """
    
    # Atributo de classe
    tier = BankTier.TIER_2
    
    # ✅ CORREÇÃO: __init__ que aceita bank_id
    def __init__(self, bank_id: str):
        """
        Inicializa InterStrategy.
        
        Args:
            bank_id: ID do banco (ex: "inter")
        """
        super().__init__(bank_id)
    
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Inter.
        
        1. Converte transaction_date (SQL format)
        2. Normaliza merchant (trim + lowercase)
        """
        # # 1. Transaction date (SQL: YYYY-MM-DD HH:MM:SS)
        # df = df.with_columns(
        #     pl.col("transaction_date")
        #     .str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S", strict=False)
        #     .fill_null(pl.col("transaction_date"))
        # )
        
        # 2. Merchant (trim + lowercase)
        # ✅ CORREÇÃO: .str.strip_chars() (API correta do Polars)
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
        Avalia qualidade dos dados do Inter.
        
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
        
        # Verifica balance (Inter normalmente envia)
        if "balance" not in df.columns or df.filter(pl.col("balance").is_null()).height > 0:
            return DataStatus.DEGRADED
        
        return DataStatus.TRUSTED