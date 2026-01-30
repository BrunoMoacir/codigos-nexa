# app/etl/bank_strategy/strategies/nubank.py

import polars as pl
from app.etl.bank_strategy.base import BankStrategy
from app.schemas.enums import BankTier, DataStatus


class NubankStrategy(BankStrategy):
    """
    Estratégia TIER_1 para Nubank (Excelente qualidade).
    
    CARACTERÍSTICAS:
        - Tier: TIER_1 (melhor qualidade do mercado)
        - Formato: BR consistente (1.500,00)
        - Data: ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
        - Campos: SEMPRE completos
    """
    
    # Atributo de classe
    tier = BankTier.TIER_1
    
    # ✅ CORREÇÃO: __init__ que aceita bank_id
    def __init__(self, bank_id: str):
        """
        Inicializa NubankStrategy.
        
        Args:
            bank_id: ID do banco (ex: "nubank")
        """
        super().__init__(bank_id)
    
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do Nubank.
        
        1. Converte transaction_date (ISO 8601)
        2. Extrai merchant da description
        3. Limpa categoria (Nubank não é confiável)
        """
        
        # 2. Extrair merchant da description
        # Ex: "COMPRA NO DÉBITO - UBER *1234" → "uber"
        # ✅ CORREÇÃO: .str.strip_chars() (API correta do Polars)
        df = df.with_columns(
            pl.col("description")
            .str.split("-")
            .list.get(-1)
            .str.replace(r"\*.*", "")
            .str.strip_chars()
            .alias("merchant")
        )
        
        # 3. Nubank envia categoria, mas não é confiável
        # Melhor usar o Classifier (CatBoost)
        if "category" in df.columns:
            df = df.with_columns(pl.lit(None).alias("category"))
        
        return df
    
    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Avalia qualidade dos dados do Nubank.
        
        TRUSTED se:
            - merchant preenchido (extraído com sucesso)
            - transaction_date válida
        
        DEGRADED se:
            - merchant null mas data válida
        
        UNTRUSTED se:
            - transaction_date inválida
        """
        # Verifica datas inválidas
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED
        
        # ✅ CORREÇÃO: Usar DataStatus.DEGRADED (não PARTIAL)
        # Verifica merchant (se conseguiu extrair)
        if df.filter(pl.col("merchant").is_null()).height > 0:
            return DataStatus.DEGRADED
        
        # ✅ CORREÇÃO: Usar DataStatus.TRUSTED (não OK)
        return DataStatus.TRUSTED