# app/etl/bank_strategy/strategies/default.py

import polars as pl
from app.forecast.etl.bank_strategy.base import BankStrategy
from app.core.schemas.enums import BankTier, DataStatus


class DefaultStrategy(BankStrategy):
    """
    Estratégia padrão para bancos desconhecidos ou não mapeados.
    
    CARACTERÍSTICAS:
        - Tier: TIER_3 (conservador)
        - Normalização: Nenhuma (aceita como está)
        - Avaliação: DEGRADED se campos básicos presentes
        - Uso: Fallback automático
    """
    
    # Atributo de classe
    tier = BankTier.TIER_3
    
    # ✅ CORREÇÃO: __init__ que aceita bank_id
    def __init__(self, bank_id: str):
        """
        Inicializa DefaultStrategy.
        
        Args:
            bank_id: ID do banco (ex: "unknown", "picpay", etc)
        """
        super().__init__(bank_id)
    
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalização genérica (nenhuma transformação específica).
        
        Para bancos desconhecidos, não sabemos quais normalizações
        aplicar, então mantemos os dados como estão.
        """
        # Nenhuma normalização específica
        return df
    
    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Avalia qualidade de forma conservadora.
        
        DEGRADED se:
            - Campos fundamentais presentes
            - (transaction_id, amount, transaction_date)
        
        UNTRUSTED se:
            - Algum campo fundamental faltando
        """
        # Campos fundamentais
        required = {"transaction_id", "amount", "transaction_date"}
        
        # Verifica se todos existem
        missing = required - set(df.columns)
        
        if missing:
            return DataStatus.UNTRUSTED
        
        # Verifica se têm valores (não são todos null)
        for field in required:
            if df.filter(pl.col(field).is_null()).height == len(df):
                return DataStatus.UNTRUSTED
        
        # Se passou, retorna DEGRADED (conservador para bancos desconhecidos)
        return DataStatus.DEGRADED