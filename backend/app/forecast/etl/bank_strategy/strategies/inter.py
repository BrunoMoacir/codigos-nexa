# app/etl/bank_strategy/strategies/inter.py

import polars as pl
from app.forecast.etl.bank_strategy.base import BankStrategy
from app.core.schemas.enums import BankTier, DataStatus


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
        Teto de confiança do Inter como FONTE (TIER_2).

        A checagem de balance saiu daqui: era por LOTE, então um único saldo
        nulo (normal em cartão de crédito) rebaixava todas as outras
        transações junto. Saldo faltando agora rebaixa só a linha afetada,
        no TransactionIngestor._apply_row_quality().
        """
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED

        if "balance" not in df.columns:
            return DataStatus.DEGRADED

        return DataStatus.TRUSTED