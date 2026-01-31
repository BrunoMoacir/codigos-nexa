import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import DataStatus, BankTier


class ItauStrategy(BankStrategy):
    """
    Estratégia TIER_3 para Itaú (Dados legados/inconsistentes).
    
    CARACTERÍSTICAS:
        - Tier: TIER_3 (exige validação cuidadosa)
        - Peculiaridade: Envia valores absolutos + flag de débito
        - Normalização: Inverte sinal se transaction_type == 'DEBIT'
    """

    tier = BankTier.TIER_3

    # ✅ CORREÇÃO 1: Adicionar __init__ para consistência
    def __init__(self, bank_id: str):
        super().__init__(bank_id)

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Itaú
        """
        
        # 1. Normalizar merchant (CAIXA ALTA → lowercase)
        if "merchant" in df.columns:
            df = df.with_columns(
                pl.col("merchant")
                .str.strip_chars()  # ✅ CORREÇÃO 2: API correta do Polars
                .str.to_lowercase()
                .alias("merchant")
            )

        # 2. Corrigir sinal do amount baseado no transaction_type
        # O Itaú frequentemente manda valor positivo com flag "DEBITO"
        if "transaction_type" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("transaction_type").str.to_uppercase().str.contains("DEBIT"))
                .then(pl.col("amount").abs() * -1) # Garante negativo
                .otherwise(pl.col("amount").abs()) # Garante positivo
                .alias("amount")
            )

        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Qualidade considerada UNTRUSTED se:
        - datas inválidas (essencial para fluxo de caixa)
        """
        
        # Verifica datas nulas
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED # ✅ CORREÇÃO 3: Enum consistente

        # Itaú é Tier 3, então mesmo se passar, retornamos DEGRADED 
        # (para forçar verificação mais atenta ou uso de Shadow Invoice)
        # ou TRUSTED se você confiar muito no parser. Vamos de TRUSTED por padrão se passar.
        return DataStatus.TRUSTED