# app/optimizer/feature_store.py
# TransactionFeatureEnricher — deriva campos comportamentais do transactions_clean
# Alimenta: detectors de viagem, foodie, MEI, investor, FSS, life events
#
# Nota: geo_city/geo_state exigem geocoding externo (fora de escopo).
# is_foreign é implementado como proxy via keyword/moeda (~90% de cobertura).

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)

# ── MCCs por subcategoria ──────────────────────────────────────────────────────
_MCC_AIRLINES = set(range(3000, 3351)) | {4511}
_MCC_TRAVEL_AGENCIES = {4722, 4723}
_MCC_HOTELS = {7011, 7012}
_MCC_CAR_RENTAL = {7512, 7513}
_MCC_TRAVEL_INSURANCE = {6300}
_MCC_INVESTMENT_BROKERS = {6211}

# ── Keywords por domínio ───────────────────────────────────────────────────────
_TRAVEL_KEYWORDS = [
    "AIRBNB", "BOOKING", "DECOLAR", "LATAM", "AZUL", "GOL",
    "EXPEDIA", "LOCALIZA", "MOVIDA", "UNIDAS", "HURB", "123MILHAS",
    "VIAJANET", "MAX MILHAS", "SUBMARINO VIAG", "CVC", "FLYTOUR",
]
_DELIVERY_KEYWORDS = ["IFOOD", "RAPPI", "UBER EATS", "LOGGI", "JAMES"]
_BROKER_KEYWORDS = [
    "XP INVESTIMENTOS", "BTG", "RICO CORRETORA", "CLEAR CORRETORA",
    "MODALMAIS", "GENIAL", "INTER INVEST", "NUINVEST",
    "TESOURODIRETO", "STN ", "TESOURO NACIONAL",
]
_B2B_KEYWORDS = [
    "OMIE", "CONTA AZUL", "BLING", "NFSE", "NOTA FISCAL",
    "MERCADO PAGO TAXAS", "IFOOD PARCEIRO", "RAPPI PARTNER",
]
_COWORKING_KEYWORDS = ["WEWORK", "REGUS", "SPACES", "COWORKING", "ROOMO"]

# Padrão para detecção de transação no exterior (proxy sem geocoding)
_FOREIGN_PATTERN = r"IOF|USD|EUR|GBP|\bDOLLAR\b|\bEURO\b|EXTERIOR|INTERNATIONAL|INTERNATIONAL"


class TransactionFeatureEnricher:
    """
    Enriquece o transactions_clean com campos derivados necessários para os
    detectores comportamentais (Fase 1+2 do User Intelligence).

    Chamado por ConsumptionProfiler.build() logo após _prepare_df().
    Retorna o mesmo DataFrame com colunas extras — não altera schema original.
    Todas as colunas adicionadas são idempotentes (não sobrescreve se já existe).
    """

    def enrich(self, df: pl.DataFrame) -> pl.DataFrame:
        df = self._add_payment_method(df)
        df = self._add_is_travel_related(df)
        df = self._add_is_delivery(df)
        df = self._add_is_broker(df)
        df = self._add_is_b2b(df)
        df = self._add_merchant_category_l2(df)
        df = self._add_is_foreign(df)
        df = self._add_temporal_features(df)
        return df

    # ── Métodos de enriquecimento ────────────────────────────────────────────

    def _add_payment_method(self, df: pl.DataFrame) -> pl.DataFrame:
        """PIX / BOLETO / TED / DEBIT / CREDIT — mais granular que transaction_type."""
        if "payment_method" in df.columns:
            return df

        if "transaction_type" not in df.columns:
            return df.with_columns(pl.lit("UNKNOWN").alias("payment_method"))

        desc_upper = (
            pl.col("description").str.to_uppercase()
            if "description" in df.columns
            else pl.lit("")
        )

        return df.with_columns(
            pl.when(desc_upper.str.contains(r"\bPIX\b"))
            .then(pl.lit("PIX"))
            .when(desc_upper.str.contains("BOLETO"))
            .then(pl.lit("BOLETO"))
            .when(desc_upper.str.contains(r"TED|DOC"))
            .then(pl.lit("TED"))
            .when(pl.col("transaction_type").str.to_uppercase() == "DEBIT")
            .then(pl.lit("DEBIT"))
            .otherwise(pl.lit("CREDIT"))
            .alias("payment_method")
        )

    def _add_is_travel_related(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação relacionada a viagem (MCC + keywords)."""
        if "is_travel_related" in df.columns:
            return df

        conditions = []

        if "mcc" in df.columns:
            all_travel_mccs = (
                _MCC_AIRLINES | _MCC_TRAVEL_AGENCIES | _MCC_HOTELS
                | _MCC_CAR_RENTAL | _MCC_TRAVEL_INSURANCE
            )
            conditions.append(pl.col("mcc").is_in(list(all_travel_mccs)))

        if "description" in df.columns:
            pattern = "|".join(_TRAVEL_KEYWORDS)
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            )

        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_travel_related"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c

        return df.with_columns(expr.alias("is_travel_related"))

    def _add_is_delivery(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: pedido em app de delivery."""
        if "is_delivery" in df.columns:
            return df
        if "description" not in df.columns:
            return df.with_columns(pl.lit(False).alias("is_delivery"))

        pattern = "|".join(_DELIVERY_KEYWORDS)
        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(pattern).alias("is_delivery")
        )

    def _add_is_broker(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação para corretora ou tesouro direto."""
        if "is_broker_txn" in df.columns:
            return df

        conditions = []
        if "mcc" in df.columns:
            conditions.append(pl.col("mcc").is_in(list(_MCC_INVESTMENT_BROKERS)))
        if "description" in df.columns:
            pattern = "|".join(_BROKER_KEYWORDS)
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            )

        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_broker_txn"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c
        return df.with_columns(expr.alias("is_broker_txn"))

    def _add_is_b2b(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: gasto em ferramenta B2B (sinal de MEI/PJ)."""
        if "is_b2b" in df.columns:
            return df
        if "description" not in df.columns:
            return df.with_columns(pl.lit(False).alias("is_b2b"))

        pattern = "|".join(_B2B_KEYWORDS)
        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(pattern).alias("is_b2b")
        )

    def _add_merchant_category_l2(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Subcategoria L2 por keyword na descrição.
        Fase 1: regras determinísticas. Fase 3: modelo ML (T3.1) complementa.
        """
        if "merchant_category_l2" in df.columns:
            return df
        if "description" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_category_l2"))

        desc = pl.col("description").str.to_uppercase()

        expr = (
            pl.when(desc.str.contains("|".join(_DELIVERY_KEYWORDS)))
            .then(pl.lit("DELIVERY"))
            .when(desc.str.contains("AIRBNB"))
            .then(pl.lit("AIRBNB"))
            .when(desc.str.contains("LOCALIZA|MOVIDA|UNIDAS|HERTZ"))
            .then(pl.lit("LOCADORA"))
            .when(desc.str.contains("LATAM|GOL|AZUL|AVIANCA|TAM"))
            .then(pl.lit("VOO"))
            .when(desc.str.contains("HOTEL|POUSADA|INN|RESORT"))
            .then(pl.lit("HOTEL"))
            .when(desc.str.contains("FARMACIA|DROGASIL|DROGA RAIA|PACHECO|ULTRAFARMA"))
            .then(pl.lit("FARMACIA"))
            .when(desc.str.contains("ACADEMIA|SMARTFIT|BLUEFIT|BODYTECH"))
            .then(pl.lit("ACADEMIA"))
            .when(desc.str.contains("ESCOLA|COLEGIO|CRECHE|UNIVERSIDADE|FACULDADE"))
            .then(pl.lit("ESCOLA"))
            .when(desc.str.contains("PEDIATR|CLINICA INFANTIL|HOSPITAL|PLANO SAUDE"))
            .then(pl.lit("SAUDE"))
            .when(desc.str.contains("|".join(_BROKER_KEYWORDS)))
            .then(pl.lit("CORRETORA"))
            .when(desc.str.contains("SUPERMERCADO|CARREFOUR|EXTRA|PAO DE ACUCAR|MERCADO"))
            .then(pl.lit("SUPERMERCADO"))
            .when(desc.str.contains("RESTAURANTE|LANCHONETE|PIZZARIA|HAMBURGER|SUSHI"))
            .then(pl.lit("RESTAURANTE"))
            .when(desc.str.contains("NETFLIX|SPOTIFY|AMAZON PRIME|DISNEY|HBO|GLOBOPLAY|DEEZER"))
            .then(pl.lit("STREAMING"))
            .when(desc.str.contains("|".join(_COWORKING_KEYWORDS)))
            .then(pl.lit("COWORKING"))
            .otherwise(pl.lit(None))
        )

        return df.with_columns(expr.alias("merchant_category_l2"))

    def _add_is_foreign(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Booleano: transação no exterior.
        Proxy via moeda != BRL ou keywords (IOF, USD, EUR...).
        Não implementa geocoding completo (exige DB externo).
        """
        if "is_foreign" in df.columns:
            return df

        conditions = []

        if "currency" in df.columns:
            conditions.append(
                pl.col("currency").is_not_null() & (pl.col("currency") != "BRL")
            )

        if "description" in df.columns:
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(_FOREIGN_PATTERN)
            )

        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_foreign"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c
        return df.with_columns(expr.alias("is_foreign"))

    def _add_temporal_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Adiciona day_of_week (0=Segunda…6=Domingo) e is_weekend.

        Verifica antes de adicionar: ingestor.py:159 já deriva day_of_week de
        transaction_date no pipeline ETL. O optimizer recebe coluna `date`,
        então o campo pode não existir neste DataFrame.
        """
        if "day_of_week" not in df.columns and "date" in df.columns:
            df = df.with_columns(
                pl.col("date").dt.weekday().alias("day_of_week"),
            )

        if "is_weekend" not in df.columns and "day_of_week" in df.columns:
            df = df.with_columns(
                (pl.col("day_of_week") >= 5).alias("is_weekend"),
            )

        return df
