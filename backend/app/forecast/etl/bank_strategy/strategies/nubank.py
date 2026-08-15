# app/etl/bank_strategy/strategies/nubank.py

import polars as pl
from app.forecast.etl.bank_strategy.base import BankStrategy
from app.core.schemas.enums import BankTier, DataStatus


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
        
        # 2. Extrair merchant da description QUANDO o banco não mandou um.
        # Ex: "COMPRA NO DÉBITO - UBER *1234" → "uber"
        #
        # Só preenche vazio: antes sobrescrevia sempre e jogava fora o
        # merchant.businessName que a Pluggy entrega no cartão — dado melhor
        # do que qualquer split de descrição.
        # `\*\d+` e não `\*.*`: o alvo é o sufixo de cartão ("UBER *1234"),
        # não tudo que vem depois do asterisco. Cortando geral, "PAG*IFOOD
        # DELIVERY" — o formato de cartão mais comum — virava merchant "pag",
        # e a chave canônica saía VAZIA (pag é ruído bancário), matando
        # agrupamento de recorrência e sinal de categoria.
        derivado = (
            pl.col("description")
            .str.split("-")
            .list.get(-1)
            .str.replace(r"\*\d+.*", "")
            .str.strip_chars()
        )

        if "merchant" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("merchant").cast(pl.String).fill_null("").str.len_chars() > 0)
                .then(pl.col("merchant"))
                .otherwise(derivado)
                .alias("merchant")
            )
        else:
            df = df.with_columns(derivado.alias("merchant"))
        
        # 3. Nubank envia categoria, mas não é confiável
        # Melhor usar o Classifier (CatBoost)
        if "category" in df.columns:
            df = df.with_columns(pl.lit(None).alias("category"))
        
        return df
    
    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Teto de confiança do Nubank como FONTE (TIER_1).

        Este método responde "dá para confiar neste banco?", não "esta linha
        está completa?" — lacuna de linha é rebaixada depois, no
        TransactionIngestor._apply_row_quality(). Antes o critério era
        `merchant.is_null()`, que nunca disparava (o ingestor preenche null
        com "" antes das strategies): o portão ficava sempre aberto.

        UNTRUSTED só quando o lote vem com data inválida — aí não é lacuna,
        é o conector quebrado.
        """
        if df.filter(pl.col("transaction_date").is_null()).height > 0:
            return DataStatus.UNTRUSTED

        return DataStatus.TRUSTED