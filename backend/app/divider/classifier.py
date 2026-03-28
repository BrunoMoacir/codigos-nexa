"""
app/etl/pf_pj_classifier.py - Classificador PF/PJ para o pipeline ETL

Integra modelo ML (Random Forest) com regras de fallback para classificar
transações como Pessoais (PF) ou Empresariais (PJ).

Uso no pipeline:
- Carrega modelo treinado + encoders/scalers
- Extrai features das transações
- Prediz com ML, usa fallback se confiança baixa
- Adiciona coluna 'pf_pj_label' ao DataFrame
"""

import polars as pl
import logging
import re
from datetime import datetime
from typing import Dict, Any

from app.divider.subcategory_classifier import get_pj_subcategory_classifier

logger = logging.getLogger(__name__)

class PFPJClassifier:
    """
    Classificador PF/PJ baseado em regras vetorizadas (Polars expressions).

    Classifica transações como Pessoais (PF), Empresariais (PJ) ou UNCERTAIN
    usando um conjunto de regras determinísticas aplicadas em batch via Polars.
    """

    def __init__(self):
        self.fallback_classifier = PFPJFallbackClassifier()

    def classify_batch(self, transactions_df: pl.DataFrame) -> pl.DataFrame:
        """
        Classifica batch de transações PF/PJ e adiciona subcategoria para PJ.

        Usa expressões Polars nativas (vetorizado) para a classificação principal,
        evitando loop Python por linha. O ML é aplicado antes se o modelo estiver
        disponível e a confiança for alta.

        Args:
            transactions_df: DataFrame com transações (depois do ETL Ingestor)

        Returns:
            DataFrame com colunas 'pf_pj_label' e 'pj_subcategory' adicionadas.
            'pj_subcategory' é None para transações PF/UNCERTAIN.
        """
        logger.info(f"Classificando {len(transactions_df)} transacoes PF/PJ...")

        fb = self.fallback_classifier

        # ── Classificação vetorizada via Polars expressions ────────────────
        # Normaliza colunas de texto para lowercase uma única vez
        desc_col = pl.col("description").fill_null("").str.to_lowercase()
        merch_col = (
            pl.col("merchant").fill_null("").str.to_lowercase()
            if "merchant" in transactions_df.columns
            else pl.lit("")
        )
        amount_abs = pl.col("amount").abs()

        # Padrões regex: une keywords com "|" para uma única passagem por linha
        pj_kw  = "|".join(re.escape(k) for k in fb.pj_keywords)
        pf_kw  = "|".join(re.escape(k) for k in fb.pf_keywords)
        pj_mch = "|".join(re.escape(m) for m in ["microsoft", "fornecedor", "imobiliaria", "cemig", "contador"])
        pf_mch = "|".join(re.escape(m) for m in ["uber", "netflix", "starbucks", "cinepolis", "spotify"])

        label_expr = (
            pl.when(pl.col("category").fill_null("").is_in(fb.pj_categories))
            .then(pl.lit("PJ"))
            .when(desc_col.str.contains(pj_kw))
            .then(pl.lit("PJ"))
            .when(amount_abs > 2000)
            .then(pl.lit("PJ"))
            .when(desc_col.str.contains(pf_kw))
            .then(pl.lit("PF"))
            .when(merch_col.str.contains(pj_mch))
            .then(pl.lit("PJ"))
            .when(merch_col.str.contains(pf_mch))
            .then(pl.lit("PF"))
            .otherwise(pl.lit("UNCERTAIN"))
        )

        classifications = (
            transactions_df
            .with_columns(label_expr.alias("pf_pj_label"))
            ["pf_pj_label"]
            .to_list()
        )

        # Subcategoria PJ: map_elements apenas nas linhas rotuladas como PJ
        pj_classifier = get_pj_subcategory_classifier()
        rows_for_subcat = list(transactions_df.iter_rows(named=True))
        subcategories = [
            pj_classifier.classify(row) if label == "PJ" else None
            for row, label in zip(rows_for_subcat, classifications)
        ]

        result_df = transactions_df.with_columns([
            pl.Series("pf_pj_label", classifications),
            pl.Series("pj_subcategory", subcategories),
        ])

        pf_count = classifications.count("PF")
        pj_count = classifications.count("PJ")
        uncertain_count = classifications.count("UNCERTAIN")

        logger.info(f"Classificacao completa: PF={pf_count}, PJ={pj_count}, UNCERTAIN={uncertain_count}")

        return result_df

class PFPJFallbackClassifier:
    """
    Classificador rule-based (mesmo código de pf_pj_fallback_rules.py)
    """

    def __init__(self):
        self.pj_keywords = [
            'empresa', 'ltda', 'fornecedor', 'aluguel', 'escritorio', 'imobiliaria',
            'viagem negocios', 'software', 'corporativo', 'marketing', 'cemig empresas',
            'consultoria', 'contador', 'salario', 'papelaria'
        ]
        self.pf_keywords = [
            'uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
            'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
            'pet shop', 'livraria', 'pix recebido', 'amigo'
        ]
        self.pj_categories = [
            'SALARY', 'OFFICE_SUPPLIES', 'RENT', 'SOFTWARE', 'CONSULTING',
            'MARKETING', 'UTILITIES', 'TELEPHONE'
        ]

    def classify(self, transaction: Dict[str, Any]) -> str:
        """Classifica usando regras determinísticas"""
        description = transaction.get('description', '') or ''
        category = transaction.get('category', '') or ''
        amount = transaction.get('amount', 0) or 0
        transaction_date = transaction.get('transaction_date')
        hour_of_day = 12  # default
        if isinstance(transaction_date, datetime):
            hour_of_day = transaction_date.hour
        elif isinstance(transaction_date, str):
            try:
                parsed_date = datetime.fromisoformat(transaction_date.replace('Z', '+00:00'))
                hour_of_day = parsed_date.hour
            except:
                pass
        merchant = transaction.get('merchant', '') or ''

        # Converte para tipos apropriados
        description = description.lower()
        merchant = merchant.lower()
        amount = abs(amount)

        # Regras de alta prioridade
        if category in self.pj_categories:
            return 'PJ'

        if any(kw in description for kw in self.pj_keywords):
            return 'PJ'

        if amount > 2000:
            return 'PJ'

        if any(kw in description for kw in self.pf_keywords):
            return 'PF'

        if amount < 20 and (hour_of_day < 8 or hour_of_day > 18):
            return 'PF'

        # Merchants conhecidos
        if any(m in merchant for m in ['microsoft', 'fornecedor', 'imobiliaria', 'cemig', 'contador']):
            return 'PJ'
        if any(m in merchant for m in ['uber', 'netflix', 'starbucks', 'cinepolis', 'spotify']):
            return 'PF'

        return 'UNCERTAIN'