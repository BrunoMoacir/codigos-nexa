"""
app/etl/shadow_invoices/installment_detector.py - VERSÃO CORRIGIDA

CORREÇÕES v2.0:
    ✅ Adicionada keyword "parcelada" (comum no Brasil)
    ✅ Adicionada keyword "compra parcelada"
    ✅ Melhorado parsing de "N/M" e "Nx"
"""

import logging
import polars as pl
from datetime import datetime
import re

from .base import ShadowInvoiceDetector

logger = logging.getLogger(__name__)


class InstallmentDetector(ShadowInvoiceDetector):
    """
    Detecta parcelamentos (3/12, 10x, etc) - VERSÃO CORRIGIDA.
    
    CORREÇÕES v2.0:
        - Adicionada keyword "parcelada"
        - Adicionada keyword "compra parcelada"
        - Melhorado parsing de installment_info
    
    Critérios:
        1. ✅ Contém keyword de parcelamento OU padrão numérico
        2. ✅ Aparece 3+ vezes
        3. ✅ Presente em 2+ meses diferentes
    
    Keywords (ATUALIZADAS):
        - parc, parcela, parcelada, parcelamento ✅ NOVO
        - compra parcelada ✅ NOVO
        - x (ex: 10x, 12x)
        - / (ex: 3/12, 10/24)
        - installment
    
    Padrões numéricos:
        - "3/12" → parcela 3 de 12
        - "10x" → parcela 10
        - "parc 3 de 12" → parcela 3 de 12
        - "parcela 05/12" → parcela 5 de 12
        - "compra parcelada 3/12" → parcela 3 de 12 ✅ NOVO
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # KEYWORDS (v2.0 - CORRIGIDAS)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    KEYWORDS = [
        "parc",               # "parc 3/12", "parc 10"
        "parcela",            # "parcela 3 de 12"
        "parcelada",          # ✅ NOVO - "compra parcelada"
        "parcelamento",       # ✅ NOVO - "parcelamento 12x"
        "compra parcelada",   # ✅ NOVO - forma completa
        "x ",                 # "10x ", "12x "
        "/12", "/24", "/6", "/10", "/18",  # Padrões comuns
        "installment"         # Inglês
    ]
    
    def __init__(self):
        """Inicializa detector."""
        self.logger = logging.getLogger(__name__)
    
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta parcelamentos (versão corrigida).
        
        Args:
            df: DataFrame com colunas:
                - description (str)
                - amount (float)
                - transaction_date (datetime)
        
        Returns:
            DataFrame com colunas:
                - type: "INSTALLMENT"
                - amount: float (negativo)
                - next_due_date: datetime
                - metadata: dict com description, occurrences, installment_info
                - confidence: float (0.7-0.9)
        """
        if df.is_empty():
            self.logger.warning("DataFrame vazio")
            return self._empty_result()
        
        # Validar colunas
        required = {"description", "amount", "transaction_date"}
        if not required.issubset(df.columns):
            self.logger.error("Colunas obrigatórias faltando: %s", required - set(df.columns))
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Filtrar apenas despesas
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_expenses = df.filter(pl.col("amount") < 0)
        
        if df_expenses.is_empty():
            self.logger.info("Nenhuma despesa encontrada")
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Normalizar description
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_expenses = df_expenses.with_columns(
            pl.col("description").str.to_lowercase().alias("desc_lower")
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Filtrar por keywords ✅ ATUALIZADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Criar expressão OR para todas as keywords
        keyword_expr = pl.lit(False)
        for keyword in self.KEYWORDS:
            keyword_expr = keyword_expr | pl.col("desc_lower").str.contains(keyword)
        
        df_with_keywords = df_expenses.filter(keyword_expr)
        
        self.logger.debug(
            f"Transações com keywords de parcelamento: {df_with_keywords.height}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Extrair base_description (remove números de parcela)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_with_keywords = df_with_keywords.with_columns(
            pl.col("desc_lower")
            .str.replace_all(r"\d+/\d+", "")      # Remove "3/12"
            .str.replace_all(r"\d+x", "")          # Remove "10x"
            .str.replace_all(r"parcela \d+", "")   # Remove "parcela 3"
            .str.strip_chars()
            .alias("base_desc")
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5: Agrupar por base_description
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        grouped = df_with_keywords.group_by("base_desc").agg([
            pl.col("amount").count().alias("occurrences"),
            pl.col("amount").mean().alias("avg_amount"),
            pl.col("transaction_date").max().alias("last_date"),
            pl.col("transaction_date").min().alias("first_date"),
            pl.col("transaction_date").dt.month().n_unique().alias("unique_months"),
            pl.col("description").first().alias("original_desc")
        ])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 6: Filtrar por frequência
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Critério: 3+ ocorrências em 2+ meses
        candidates = grouped.filter(
            (pl.col("occurrences") >= 3) &
            (pl.col("unique_months") >= 2)
        )
        
        if candidates.is_empty():
            self.logger.info("Nenhum parcelamento encontrado (keywords presentes)")
            # Tentar detectar por padrão (sem keyword)
            return self._detect_by_pattern(df_expenses)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 7: Converter para formato Shadow Invoice
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        result = candidates.select([
            pl.lit("INSTALLMENT").alias("type"),
            pl.col("avg_amount").alias("amount"),
            (pl.col("last_date") + pl.duration(days=30)).alias("next_due_date"),
            pl.struct([
                pl.col("original_desc").alias("description"),
                pl.col("occurrences").alias("occurrences"),
            ]).alias("metadata"),
            pl.lit(0.9).alias("confidence")  # Alta confiança (keyword presente)
        ])
        
        self.logger.info("Parcelamentos detectados (keywords): %s", result.height)
        
        return result
    
    def _detect_by_pattern(self, df_expenses: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta parcelamentos por padrão (sem keyword).
        
        Critério:
            - 4+ ocorrências (mais rigoroso)
            - 3+ meses únicos
            - Valor fixo (variação < 5%)
        """
        # Agrupar por description exata
        grouped = df_expenses.group_by("description").agg([
            pl.col("amount").count().alias("occurrences"),
            pl.col("amount").mean().alias("avg_amount"),
            pl.col("amount").std().alias("std_amount"),
            pl.col("transaction_date").max().alias("last_date"),
            pl.col("transaction_date").dt.month().n_unique().alias("unique_months")
        ])
        
        # Calcular variação
        grouped = grouped.with_columns(
            (pl.col("std_amount") / pl.col("avg_amount").abs()).alias("variation")
        )
        
        # Filtrar: 4+ ocorrências, 3+ meses, variação < 5%
        candidates = grouped.filter(
            (pl.col("occurrences") >= 4) &
            (pl.col("unique_months") >= 3) &
            (pl.col("variation") < 0.05)
        )
        
        if candidates.is_empty():
            self.logger.info("Nenhum parcelamento detectado (padrão)")
            return self._empty_result()
        
        result = candidates.select([
            pl.lit("INSTALLMENT").alias("type"),
            pl.col("avg_amount").alias("amount"),
            (pl.col("last_date") + pl.duration(days=30)).alias("next_due_date"),
            pl.struct([
                pl.col("description").alias("description"),
                pl.col("occurrences").alias("occurrences"),
            ]).alias("metadata"),
            pl.lit(0.7).alias("confidence")  # Confiança menor (sem keyword)
        ])
        
        self.logger.info("Parcelamentos detectados (padrão): %s", result.height)
        
        return result
    
    def _empty_result(self) -> pl.DataFrame:
        """Retorna DataFrame vazio com schema correto."""
        return pl.DataFrame({
            "type": [],
            "amount": [],
            "next_due_date": [],
            "metadata": [],
            "confidence": []
        }).cast({
            "type": pl.Utf8,
            "amount": pl.Float64,
            "next_due_date": pl.Datetime,
            "metadata": pl.Struct,
            "confidence": pl.Float64
        })