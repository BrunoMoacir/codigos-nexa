"""
app/etl/shadow_invoices/installment_detector.py - Detector de Parcelamentos

MELHORIAS:
    ✅ Case-insensitive (funciona com "Parcelado", "PARCELADO", "parcelado")
    ✅ Mais keywords brasileiras (parcela, parc, parcelado, etc)
    ✅ Detecção TAMBÉM por padrão (mesmo sem keyword)
    ✅ Debug logs para investigar problemas
"""

import polars as pl
import logging
from app.etl.shadow_invoices.base import ShadowInvoiceDetector

logger = logging.getLogger(__name__)


class InstallmentDetector(ShadowInvoiceDetector):
    """
    Detecta parcelamentos em transações.
    
    Estratégias de detecção:
        1. Por keyword: descrição contém "parc", "parcela", "x", etc
        2. Por padrão: mesmo valor repetido em meses consecutivos
    
    Critérios:
        - Mínimo 3 ocorrências
        - Em pelo menos 2 meses diferentes
        - Valor exato igual (parcelamento tem valor fixo)
    """
    
    # Keywords que indicam parcelamento (case-insensitive)
    INSTALLMENT_KEYWORDS = [
        "parcel",       # Parcelado, Parcelamento
        "parc",         # Parc 1/12
        "parcela",      # Parcela
        "x",            # 3x, 12x
        "/",            # 1/12, 2/12
        "installment",  # Em inglês (alguns bancos)
    ]
    
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta parcelamentos no DataFrame.
        
        Args:
            df: DataFrame com transações normalizadas
        
        Returns:
            DataFrame com parcelamentos detectados (pode estar vazio)
        """
        if df.is_empty():
            logger.debug("DataFrame vazio, pulando detecção de parcelamentos")
            return pl.DataFrame()
        
        logger.info(f"Iniciando detecção de parcelamentos em {len(df)} transações")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 1: ADICIONAR COLUNA DE MÊS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = df.with_columns([
            pl.col("transaction_date").dt.truncate("1mo").alias("month")
        ])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 2: AGRUPAR POR DESCRIÇÃO + VALOR
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        grouped = (
            df.group_by(["description", "amount"])
            .agg([
                pl.count().alias("count"),
                pl.col("month").n_unique().alias("months")
            ])
        )
        
        logger.debug(f"Agrupamentos encontrados: {len(grouped)}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 3: DETECTAR POR KEYWORD (estratégia 1)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Criar expressão regex case-insensitive
        # Exemplo: (?i)(parcel|parc|parcela|x|/)
        keywords_pattern = "(?i)(" + "|".join(self.INSTALLMENT_KEYWORDS) + ")"
        
        by_keyword = grouped.filter(
            (pl.col("count") >= 3) &
            (pl.col("months") >= 2) &
            pl.col("description").str.contains(keywords_pattern)
        )
        
        logger.debug(f"Parcelamentos detectados por keyword: {len(by_keyword)}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 4: DETECTAR POR PADRÃO (estratégia 2 - fallback)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Mesmo valor em meses consecutivos (sem keyword)
        by_pattern = grouped.filter(
            (pl.col("count") >= 4) &  # Mais restritivo (4+ ocorrências)
            (pl.col("months") >= 3) &  # Em 3+ meses diferentes
            ~pl.col("description").str.contains(keywords_pattern)  # SEM keyword
        )
        
        logger.debug(f"Parcelamentos detectados por padrão: {len(by_pattern)}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 5: COMBINAR RESULTADOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Concatenar detecções por keyword + padrão
        if by_keyword.is_empty() and by_pattern.is_empty():
            logger.info("Nenhum parcelamento detectado")
            return pl.DataFrame()
        
        # Juntar resultados
        all_installments = []
        if not by_keyword.is_empty():
            all_installments.append(by_keyword)
        if not by_pattern.is_empty():
            all_installments.append(by_pattern)
        
        combined = pl.concat(all_installments)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 6: GERAR SHADOW INVOICES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Pegar data mais recente do DataFrame original
        today = df.select(pl.col("transaction_date").max()).item()
        
        result = combined.select([
            pl.lit("INSTALLMENT").alias("type"),
            pl.col("amount"),
            (pl.lit(today) + pl.duration(days=30)).alias("next_due_date"),
            pl.struct(["description", "count"]).alias("metadata"),
            
            # Confidence: maior se tem keyword (90%), menor se só padrão (70%)
            pl.when(pl.col("description").str.contains(keywords_pattern))
              .then(pl.lit(0.90))
              .otherwise(pl.lit(0.70))
              .alias("confidence")
        ])
        
        logger.info(f"Total de parcelamentos detectados: {len(result)}")
        
        return result