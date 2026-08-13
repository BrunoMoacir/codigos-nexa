# app/etl/bank_strategy/strategies/itau.py
import polars as pl
from app.forecast.etl.bank_strategy.base import BankStrategy
from app.core.schemas.enums import DataStatus, BankTier


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

        # 2. Corrigir sinal do amount baseado na flag de débito/crédito.
        # O Itaú frequentemente manda valor positivo com flag "DEBITO".
        #
        # A coluna é `type` (campo do schema). Estava escrito
        # "transaction_type", que só nasce no PASSO 7 do ingestor — depois
        # desta strategy rodar: a correção nunca era aplicada.
        if "type" in df.columns:
            flag = pl.col("type").cast(pl.String).fill_null("").str.to_uppercase()
            df = df.with_columns(
                pl.when(flag.str.contains("DEBIT"))
                .then(pl.col("amount").abs() * -1)   # Garante negativo
                .when(flag.str.contains("CREDIT"))
                .then(pl.col("amount").abs())        # Garante positivo
                .otherwise(pl.col("amount"))         # Sem flag: não adivinha
                .alias("amount")
            )

        return df

    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Avalia qualidade dos dados do Itaú.
    
        Itaú é TIER_3 (problemático):
        - Bugs conhecidos (sinais invertidos)
        - Balance faltando ocasionalmente
        - Formato BR inconsistente
    
        DEGRADED se:
        - Datas válidas (passam validação básica)
        - Itaú sempre é TIER_3 (conservador)
    
        UNTRUSTED se:
        - Datas inválidas
        """
        # Verifica datas inválidas
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED
    
        # ✅ CORREÇÃO: Itaú é TIER_3, sempre retorna DEGRADED
        # (força uso de Shadow Invoice para preenchimento de lacunas)
        return DataStatus.DEGRADED