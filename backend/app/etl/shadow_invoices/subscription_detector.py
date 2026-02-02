"""
app/etl/shadow_invoices/subscription_detector.py - v4 (Schema padronizado)

CORREÇÃO:
    ✅ Metadata padronizado: {"description", "occurrences"}
    ✅ Compatible com InstallmentDetector para concat
"""

import polars as pl
import logging
from app.etl.shadow_invoices.base import ShadowInvoiceDetector

logger = logging.getLogger(__name__)


class SubscriptionDetector(ShadowInvoiceDetector):
    """Detecta assinaturas (pagamentos recorrentes com valor fixo)."""
    
    MAX_STD_RATIO = 0.10  # 10%
    
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
            logger.debug("DataFrame vazio, pulando detecção de assinaturas")
            return pl.DataFrame()
        
        logger.info(f"Iniciando detecção de assinaturas em {len(df)} transações")
        
        df = df.with_columns([
            pl.col("transaction_date").dt.truncate("1mo").alias("month")
        ])
        
        grouped = (
            df.group_by("description")
            .agg([
                pl.col("amount").mean().alias("avg_amount"),
                pl.col("amount").std().alias("std_amount"),
                pl.col("month").n_unique().alias("months")
            ])
        )
        
        logger.debug(f"Agrupamentos por descrição: {len(grouped)}")
        
        for row in grouped.iter_rows(named=True):
            avg = row["avg_amount"]
            std = row["std_amount"]

            avg_str = f"{avg:.2f}" if avg is not None else "N/A"
            std_str = f"{std:.2f}" if std is not None else "N/A"
            
            logger.debug(
                f"  {row['description']}: "
                f"avg={avg_str}, "
                f"std={std_str}, "
                f"months={row['months']}"
            )
        
        installment_pattern = "(?i)(" + "|".join(self.INSTALLMENT_KEYWORDS) + ")"
        
        subscriptions = grouped.filter(
            (pl.col("months") >= 3) &
            (pl.col("std_amount") <= (pl.col("avg_amount").abs() * self.MAX_STD_RATIO)) &
            ~pl.col("description").str.contains(installment_pattern)
        )
        
        logger.debug(f"Assinaturas detectadas (após excluir parcelamentos): {len(subscriptions)}")
        
        if subscriptions.is_empty():
            logger.info("Nenhuma assinatura detectada")
            return pl.DataFrame()
        
        today = df.select(pl.col("transaction_date").max()).item()
        
        # ✅ CORRIGIDO: Usar "occurrences" em vez de "months"
        result = subscriptions.select([
            pl.lit("SUBSCRIPTION").alias("type"),
            pl.col("avg_amount").alias("amount"),
            (pl.lit(today) + pl.duration(days=30)).alias("next_due_date"),
            # ✅ PADRONIZADO: description + occurrences
            pl.struct([
                pl.col("description").alias("description"),
                pl.col("months").alias("occurrences")  # ← Renomeado para "occurrences"
            ]).alias("metadata"),
            pl.lit(0.9).alias("confidence")
        ])
        
        logger.info(f"Total de assinaturas detectadas: {len(result)}")
        
        return result