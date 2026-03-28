"""
app/etl/shadow_invoices/subscription_detector.py - VERSÃO CORRIGIDA

CORREÇÕES v2.0:
    ✅ Filtra apenas categorias elegíveis (streaming, software, cloud)
    ✅ Exclui contas de consumo (luz, água, gás)
    ✅ Exclui despesas fixas (aluguel, condomínio, escola)
    ✅ Keywords positivas (netflix, spotify, amazon, google)
    ✅ Keywords negativas (aluguel, condominio, enel, sabesp, agua, luz)
"""

import logging
import polars as pl
from datetime import datetime
from typing import Optional

from .base import ShadowInvoiceDetector

logger = logging.getLogger(__name__)


class SubscriptionDetector(ShadowInvoiceDetector):
    """
    Detecta assinaturas (Netflix, Spotify, etc) - VERSÃO CORRIGIDA.
    
    CORREÇÕES v2.0:
        - Filtra apenas categorias elegíveis
        - Exclui contas de consumo variável
        - Exclui despesas fixas (aluguel, condomínio)
        - Usa keywords positivas E negativas
    
    Critérios (TODOS devem ser satisfeitos):
        1. ✅ Valor fixo (variação < 10%)
        2. ✅ Mensal (3+ meses consecutivos)
        3. ✅ Categoria elegível OU keyword positiva
        4. ❌ NÃO contém keyword negativa
        5. ❌ NÃO contém keyword de parcelamento
    
    Categorias elegíveis:
        - Lazer (streaming: Netflix, Spotify, Prime)
        - Outros (software: Dropbox, Adobe, Office)
    
    Keywords positivas (streaming/software):
        - netflix, spotify, amazon prime, youtube, disney
        - google, microsoft, apple, adobe, dropbox
        - zoom, slack, notion, trello
    
    Keywords negativas (contas/despesas fixas):
        - aluguel, condominio, imovel, casa
        - enel, cemig, copel, celesc (luz)
        - sabesp, sanepar, cedae (água)
        - boleto, conta, fatura
        - escola, faculdade, mensalidade
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # KEYWORDS (v2.0 - CORRIGIDAS)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Serviços de streaming/software (POSITIVAS)
    POSITIVE_KEYWORDS = [
        # Streaming
        "netflix", "spotify", "amazon prime", "prime video",
        "youtube premium", "disney", "hbo", "globoplay",
        "paramount", "apple tv", "apple music", "deezer",
        
        # Cloud/Software
        "google one", "google drive", "icloud", "onedrive",
        "dropbox", "microsoft 365", "office 365",
        "adobe", "creative cloud",
        
        # Produtividade
        "notion", "evernote", "todoist", "trello",
        "asana", "slack", "zoom", "teams",
        
        # Outros
        "kindle unlimited", "audible", "scribd"
    ]
    
    # Contas e despesas fixas (NEGATIVAS - EXCLUIR)
    NEGATIVE_KEYWORDS = [
        # Moradia
        "aluguel", "imovel", "condominio", "iptu",
        "casa", "apartamento", "locacao",
        
        # Utilities (consumo variável)
        "enel", "cemig", "copel", "celesc", "light",  # Luz
        "sabesp", "sanepar", "cedae", "embasa",       # Água
        "comgas", "gas", "botijao",                   # Gás
        "conta luz", "conta de luz", "energia eletrica",
        "conta agua", "conta de agua",
        
        # Genéricos
        "boleto", "fatura", "mensalidade",
        "escola", "faculdade", "colegio", "curso",
        "plano saude", "convenio", "seguro"
    ]
    
    # Categorias elegíveis
    ELIGIBLE_CATEGORIES = [
        "Lazer",           # Streaming
        "Outros"           # Software/Cloud
    ]
    
    def __init__(self):
        """Inicializa detector."""
        self.logger = logging.getLogger(__name__)
    
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta assinaturas (versão corrigida).
        
        Args:
            df: DataFrame com colunas:
                - description (str)
                - amount (float)
                - transaction_date (datetime)
                - predicted_category (str) - OPCIONAL mas recomendado
        
        Returns:
            DataFrame com colunas:
                - type: "SUBSCRIPTION"
                - amount: float (negativo)
                - next_due_date: datetime
                - metadata: dict com description, occurrences
                - confidence: float (0.9)
        """
        if df.is_empty():
            self.logger.warning("DataFrame vazio")
            return self._empty_result()
        
        # Validar colunas
        if "description" not in df.columns or "amount" not in df.columns:
            self.logger.error("Colunas description e amount são obrigatórias")
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
        # STEP 3: FILTRO 1 - Excluir keywords negativas ✅ NOVO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_filtered = df_expenses
        
        for keyword in self.NEGATIVE_KEYWORDS:
            df_filtered = df_filtered.filter(
                ~pl.col("desc_lower").str.contains(keyword)
            )
        
        self.logger.debug(
            f"Após filtro de keywords negativas: {df_filtered.height} transações"
        )
        
        if df_filtered.is_empty():
            self.logger.info("Todas as transações foram filtradas (keywords negativas)")
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: FILTRO 2 - Apenas categorias elegíveis OU keywords positivas
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Verificar se coluna predicted_category existe
        has_category = "predicted_category" in df_filtered.columns
        
        if has_category:
            # Filtrar por categoria OU keyword positiva
            df_filtered = df_filtered.filter(
                pl.col("predicted_category").is_in(self.ELIGIBLE_CATEGORIES) |
                self._has_positive_keyword_expr()
            )
        else:
            # Apenas keyword positiva
            df_filtered = df_filtered.filter(
                self._has_positive_keyword_expr()
            )
        
        self.logger.debug(
            f"Após filtro de categorias/keywords: {df_filtered.height} transações"
        )
        
        if df_filtered.is_empty():
            self.logger.info("Nenhuma transação elegível encontrada")
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5: Excluir parcelamentos (mesmo filtro original)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        installment_keywords = [
            "parc", "parcela", "x ", "/12", "/24", "/6", "/10",
            "installment"
        ]
        
        for keyword in installment_keywords:
            df_filtered = df_filtered.filter(
                ~pl.col("desc_lower").str.contains(keyword)
            )
        
        if df_filtered.is_empty():
            self.logger.info("Nenhuma assinatura após filtro de parcelamentos")
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 6: Agrupar por description (resto igual)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        grouped = df_filtered.group_by("desc_lower").agg([
            pl.col("amount").count().alias("occurrences"),
            pl.col("amount").mean().alias("avg_amount"),
            pl.col("amount").std().alias("std_amount"),
            pl.col("transaction_date").max().alias("last_date"),
            pl.col("transaction_date").min().alias("first_date"),
            pl.col("description").first().alias("original_desc")
        ])
        
        # Calcular meses únicos
        grouped = grouped.with_columns([
            ((pl.col("last_date") - pl.col("first_date")).dt.total_days() / 30).alias("months_span")
        ])
        
        # Filtrar: 3+ ocorrências em 3+ meses
        candidates = grouped.filter(
            (pl.col("occurrences") >= 3) &
            (pl.col("months_span") >= 2.5)
        )
        
        if candidates.is_empty():
            self.logger.info("Nenhuma assinatura encontrada após filtros de frequência")
            return self._empty_result()
        
        # Filtrar: variação < 10%
        candidates = candidates.with_columns(
            (pl.col("std_amount") / pl.col("avg_amount").abs()).alias("variation")
        )
        
        subscriptions = candidates.filter(
            pl.col("variation") < 0.10
        )
        
        if subscriptions.is_empty():
            self.logger.info("Nenhuma assinatura com valor fixo encontrada")
            return self._empty_result()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 7: Converter para formato Shadow Invoice
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        result = subscriptions.select([
            pl.lit("SUBSCRIPTION").alias("type"),
            pl.col("avg_amount").alias("amount"),
            (pl.col("last_date") + pl.duration(days=30)).alias("next_due_date"),
            pl.struct([
                pl.col("original_desc").alias("description"),
                pl.col("occurrences").alias("occurrences")
            ]).alias("metadata"),
            pl.lit(0.9).alias("confidence")
        ])
        
        self.logger.info("Assinaturas detectadas: %s", result.height)
        
        return result
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _has_positive_keyword_expr(self) -> pl.Expr:
        """Cria expressão Polars para verificar keywords positivas."""
        # Criar expressão OR para todas as keywords
        expr = pl.lit(False)
        
        for keyword in self.POSITIVE_KEYWORDS:
            expr = expr | pl.col("desc_lower").str.contains(keyword)
        
        return expr
    
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