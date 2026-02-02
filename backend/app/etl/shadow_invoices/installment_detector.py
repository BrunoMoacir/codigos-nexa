"""
app/etl/shadow_invoices/installment_detector.py - v3 (Schema padronizado)

CORREÇÃO:
    ✅ Metadata padronizado: {"description", "occurrences"}
    ✅ Compatible com SubscriptionDetector para concat
"""

import polars as pl
import logging
from app.etl.shadow_invoices.base import ShadowInvoiceDetector

logger = logging.getLogger(__name__)


class InstallmentDetector(ShadowInvoiceDetector):
    """Detecta parcelamentos em transações."""
    
    INSTALLMENT_KEYWORDS = [
        r"\bparcel",
        r"\bparc\b",
        r"\bparcela",
        r"\d+x\b",
        r"\d+/\d+",
        r"\binstallment",
    ]
    
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            logger.debug("DataFrame vazio, pulando detecção de parcelamentos")
            return pl.DataFrame()
        
        logger.info(f"Iniciando detecção de parcelamentos em {len(df)} transações")
        
        df = df.with_columns([
            pl.col("transaction_date").dt.truncate("1mo").alias("month")
        ])
        
        grouped = (
            df.group_by(["description", "amount"])
            .agg([
                pl.len().alias("count"),
                pl.col("month").n_unique().alias("months")
            ])
        )
        
        logger.debug(f"Agrupamentos encontrados: {len(grouped)}")
        
        keywords_pattern = "(?i)(" + "|".join(self.INSTALLMENT_KEYWORDS) + ")"
        
        by_keyword = grouped.filter(
            (pl.col("count") >= 3) &
            (pl.col("months") >= 2) &
            pl.col("description").str.contains(keywords_pattern)
        )
        
        logger.debug(f"Parcelamentos detectados por keyword: {len(by_keyword)}")
        
        by_pattern = grouped.filter(
            (pl.col("count") >= 4) &
            (pl.col("months") >= 3) &
            ~pl.col("description").str.contains(keywords_pattern)
        )
        
        logger.debug(f"Parcelamentos detectados por padrão: {len(by_pattern)}")
        
        if by_keyword.is_empty() and by_pattern.is_empty():
            logger.info("Nenhum parcelamento detectado")
            return pl.DataFrame()
        
        all_installments = []
        if not by_keyword.is_empty():
            all_installments.append(by_keyword)
        if not by_pattern.is_empty():
            all_installments.append(by_pattern)
        
        combined = pl.concat(all_installments)
        
        today = df.select(pl.col("transaction_date").max()).item()
        
        # ✅ CORRIGIDO: Usar "occurrences" em vez de "count"
        result = combined.select([
            pl.lit("INSTALLMENT").alias("type"),
            pl.col("amount"),
            (pl.lit(today) + pl.duration(days=30)).alias("next_due_date"),
            # ✅ PADRONIZADO: description + occurrences
            pl.struct([
                pl.col("description").alias("description"),
                pl.col("count").alias("occurrences")  # ← Renomeado para "occurrences"
            ]).alias("metadata"),
            
            pl.when(pl.col("description").str.contains(keywords_pattern))
              .then(pl.lit(0.90))
              .otherwise(pl.lit(0.70))
              .alias("confidence")
        ])
        
        logger.info(f"Total de parcelamentos detectados: {len(result)}")
        
        return result