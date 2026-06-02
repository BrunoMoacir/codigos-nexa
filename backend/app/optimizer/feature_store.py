# app/optimizer/feature_store.py
# TransactionFeatureEnricher — deriva campos comportamentais do transactions_clean
# Alimenta: detectors de viagem, foodie, MEI, investor, FSS, life events
#
# Nota: geo_city/geo_state exigem geocoding externo (fora de escopo).
# is_foreign é implementado como proxy via keyword/moeda (~90% de cobertura).

from __future__ import annotations

import logging
import re

import polars as pl

logger = logging.getLogger(__name__)

# ── MCCs por subcategoria ──────────────────────────────────────────────────────
_MCC_AIRLINES = set(range(3000, 3351)) | {4511}
_MCC_TRAVEL_AGENCIES = {4722, 4723}
_MCC_HOTELS = {7011, 7012}
_MCC_CAR_RENTAL = {7512, 7513}
_MCC_TRAVEL_INSURANCE = {6300}
_MCC_INVESTMENT_BROKERS = {6211}

# ── Taxonomia canônica de categorias ─────────────────────────────────────────
# Formato: lowercase sem acento — igual ao knowledge_cards.json (cashback rules).
# Fonte única de verdade: qualquer consumer usa estas constantes, não strings inline.

# Mapeamento L2 → L1 (merchant_category_l1)
# Mantém SUPERMERCADO e FARMACIA separados de ALIMENTACAO: cashback rules são distintos.
_L2_TO_L1: dict[str, str] = {
    "RESTAURANTE":  "alimentacao",
    "DELIVERY":     "alimentacao",
    "SUPERMERCADO": "supermercado",
    "VOO":          "viagem",
    "HOTEL":        "viagem",
    "LOCADORA":     "viagem",
    "AIRBNB":       "viagem",
    "FARMACIA":     "farmacia",
    "SAUDE":        "saude",
    "ACADEMIA":     "saude",
    "ESCOLA":       "educacao",
    "STREAMING":    "streaming",
    "COWORKING":    "outros",
    "CORRETORA":    "outros",
}

# Categorias canônicas L1 exportadas para uso nos detectors/ranking sem string literals
CAT_ALIMENTACAO  = "alimentacao"
CAT_SUPERMERCADO = "supermercado"
CAT_FARMACIA     = "farmacia"
CAT_VIAGEM       = "viagem"
CAT_SAUDE        = "saude"
CAT_EDUCACAO     = "educacao"
CAT_STREAMING    = "streaming"
CAT_TRANSPORTE   = "transporte"
CAT_LAZER        = "lazer"
CAT_FINANCAS     = "financas"
CAT_OUTROS       = "outros"

# ── Keywords por domínio (fonte única de verdade) ──────────────────────────────
# Usados tanto nos flags booleanos (is_travel_related, is_delivery, etc.)
# quanto nos classificadores L2. Não duplicar inline.
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

# Subcategorias usadas exclusivamente no classificador L2 ──────────────────────
_VOO_KEYWORDS      = ["LATAM", "GOL", "AZUL", "AVIANCA", "TAM AIR"]
_LOCADORA_KEYWORDS = ["LOCALIZA", "MOVIDA", "UNIDAS", "HERTZ"]
_HOTEL_KEYWORDS    = ["HOTEL", "POUSADA", "INN ", "RESORT"]
_FARMACIA_KEYWORDS = ["FARMACIA", "DROGASIL", "DROGA RAIA", "PACHECO", "ULTRAFARMA"]
_ACADEMIA_KEYWORDS = ["ACADEMIA", "SMARTFIT", "BLUEFIT", "BODYTECH"]
_ESCOLA_KEYWORDS   = ["ESCOLA", "COLEGIO", "CRECHE", "UNIVERSIDADE", "FACULDADE"]
_SAUDE_KEYWORDS    = ["PEDIATR", "CLINICA INFANTIL", "HOSPITAL", "PLANO SAUDE"]
_SUPERMERCADO_KEYWORDS = ["SUPERMERCADO", "CARREFOUR", "EXTRA ", "PAO DE ACUCAR", "MERCADO"]
_RESTAURANTE_KEYWORDS  = ["RESTAURANTE", "LANCHONETE", "PIZZARIA", "HAMBURGER", "SUSHI"]
_STREAMING_KEYWORDS    = ["NETFLIX", "SPOTIFY", "AMAZON PRIME", "DISNEY", "HBO", "GLOBOPLAY", "DEEZER"]

# ── Tabela de aliases de merchant — padrão regex → merchant_id canônico ────────
# Ordem: variante mais específica antes da marca genérica.
# Padrões matcheados contra merchant_normalized (uppercase, sem prefixo de pagamento).
_MERCHANT_ALIASES: list[tuple[str, str]] = [
    # Streaming — específico antes do catch-all da marca
    (r"AMAZON\s+PRIME",          "amazon_prime"),
    (r"YOUTUBE\s+PREMIUM",       "youtube_premium"),
    (r"APPLE\s+TV",              "apple_tv"),
    (r"HBO\s*MAX",               "hbo_max"),
    (r"DISNEY",                  "disney_plus"),
    (r"NETFLIX",                 "netflix"),
    (r"SPOTIFY",                 "spotify"),
    (r"GLOBOPLAY",               "globoplay"),
    (r"DEEZER",                  "deezer"),
    (r"PARAMOUNT",               "paramount_plus"),
    (r"CRUNCHYROLL",             "crunchyroll"),
    # E-commerce / tech (AMAZON depois de AMAZON PRIME)
    (r"AMAZON",                  "amazon"),
    (r"MERCADO\s*PAGO",          "mercado_pago"),   # antes de MERCADO LIVRE
    (r"MERCADO\s*LIVRE",         "mercado_livre"),
    (r"SHOPEE",                  "shopee"),
    (r"AMERICANAS",              "americanas"),
    (r"MAGAZINE\s*LUIZA|MAGALU", "magalu"),
    (r"SUBMARINO",               "submarino"),
    # Delivery (UBER EATS antes de UBER)
    (r"UBER\s+EATS",             "uber_eats"),
    (r"IFOOD",                   "ifood"),
    (r"RAPPI",                   "rappi"),
    # Transporte (UBER depois de UBER EATS)
    (r"UBER",                    "uber"),
    (r"99\s*(?:APP|TAXI|POP)\b", "99app"),
    # Aéreas
    (r"LATAM",                   "latam"),
    (r"SMILES|GOL\b",            "gol"),
    (r"AZUL\b",                  "azul"),
    (r"AVIANCA",                 "avianca"),
    # Hospedagem
    (r"AIRBNB",                  "airbnb"),
    (r"BOOKING",                 "booking"),
    (r"DECOLAR",                 "decolar"),
    (r"HURB",                    "hurb"),
    # Locadoras
    (r"LOCALIZA",                "localiza"),
    (r"MOVIDA",                  "movida"),
    (r"UNIDAS",                  "unidas"),
    # Supermercados
    (r"CARREFOUR",               "carrefour"),
    (r"P(?:AO)?\s*DE\s*ACUCAR",  "pao_de_acucar"),
    (r"EXTRA\b",                 "extra"),
    # Farmácias
    (r"DROGASIL",                "drogasil"),
    (r"DROGA\s*RAIA",            "droga_raia"),
    (r"PACHECO",                 "pacheco"),
    (r"ULTRAFARMA",              "ultrafarma"),
    # Academias
    (r"SMART\s*FIT",             "smartfit"),
    (r"BLUE\s*FIT",              "bluefit"),
    (r"BODYTECH",                "bodytech"),
    # Investimentos
    (r"XP\s+INVESTIMENTOS",      "xp"),
    (r"NUINVEST|NU\s+INVEST",    "nuinvest"),
    (r"BTG\s*(?:PACTUAL)?",      "btg"),
    (r"RICO\s*CORRETORA",        "rico"),
    # Bancos / fintechs
    (r"NUBANK",                  "nubank"),
    # Telecom
    (r"CLARO\b",                 "claro"),
    (r"VIVO\b",                  "vivo"),
    # Apple genérico (depois de APPLE TV)
    (r"APPLE",                   "apple"),
]

# ── Padrões regex pré-compilados (re.escape em keywords literais) ──────────────
# Listas de keywords literais são escapadas para evitar que caracteres como
# espaços, pontos ou parênteses em nomes de merchants sejam interpretados como
# metacaracteres regex.
def _kw_pattern(keywords: list[str]) -> str:
    return "|".join(re.escape(k) for k in keywords)

_P_TRAVEL      = _kw_pattern(_TRAVEL_KEYWORDS)
_P_DELIVERY    = _kw_pattern(_DELIVERY_KEYWORDS)
_P_BROKER      = _kw_pattern(_BROKER_KEYWORDS)
_P_B2B         = _kw_pattern(_B2B_KEYWORDS)
_P_COWORKING   = _kw_pattern(_COWORKING_KEYWORDS)
_P_VOO         = _kw_pattern(_VOO_KEYWORDS)
_P_LOCADORA    = _kw_pattern(_LOCADORA_KEYWORDS)
_P_HOTEL       = _kw_pattern(_HOTEL_KEYWORDS)
_P_FARMACIA    = _kw_pattern(_FARMACIA_KEYWORDS)
_P_ACADEMIA    = _kw_pattern(_ACADEMIA_KEYWORDS)
_P_ESCOLA      = _kw_pattern(_ESCOLA_KEYWORDS)
_P_SAUDE       = _kw_pattern(_SAUDE_KEYWORDS)
_P_SUPERMERCADO = _kw_pattern(_SUPERMERCADO_KEYWORDS)
_P_RESTAURANTE  = _kw_pattern(_RESTAURANTE_KEYWORDS)
_P_STREAMING    = _kw_pattern(_STREAMING_KEYWORDS)

# _FOREIGN_PATTERN não usa re.escape: contém metacaracteres intencionais (\b)
_FOREIGN_PATTERN = r"IOF|USD|EUR|GBP|\bDOLLAR\b|\bEURO\b|EXTERIOR|INTERNATIONAL"


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
        df = self._add_merchant_category_l1(df)   # depende de l2
        df = self._add_category_canonical(df)      # normaliza raw bank category
        df = self._add_merchant_normalized(df)     # nome limpo para diversidade
        df = self._add_merchant_id(df)             # ID canônico por alias/slug
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

        # Fallback pl.lit("") quando description ausente: str.contains sempre
        # retorna False em string vazia, garantindo que todos caem no ramo DEBIT/CREDIT.
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
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(_P_TRAVEL)
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

        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(_P_DELIVERY).alias("is_delivery")
        )

    def _add_is_broker(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação para corretora ou tesouro direto."""
        if "is_broker_txn" in df.columns:
            return df

        conditions = []
        if "mcc" in df.columns:
            conditions.append(pl.col("mcc").is_in(list(_MCC_INVESTMENT_BROKERS)))
        if "description" in df.columns:
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(_P_BROKER)
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

        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(_P_B2B).alias("is_b2b")
        )

    def _add_merchant_category_l2(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Subcategoria L2 por keyword na descrição.
        Usa os padrões pré-compilados (_P_*) — não duplica listas inline.
        Fase 1: regras determinísticas. Fase 3: modelo ML (T3.1) complementa.
        """
        if "merchant_category_l2" in df.columns:
            return df
        if "description" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_category_l2"))

        desc = pl.col("description").str.to_uppercase()

        expr = (
            pl.when(desc.str.contains(_P_DELIVERY))
            .then(pl.lit("DELIVERY"))
            .when(desc.str.contains("AIRBNB"))
            .then(pl.lit("AIRBNB"))
            .when(desc.str.contains(_P_LOCADORA))
            .then(pl.lit("LOCADORA"))
            .when(desc.str.contains(_P_VOO))
            .then(pl.lit("VOO"))
            .when(desc.str.contains(_P_HOTEL))
            .then(pl.lit("HOTEL"))
            .when(desc.str.contains(_P_FARMACIA))
            .then(pl.lit("FARMACIA"))
            .when(desc.str.contains(_P_ACADEMIA))
            .then(pl.lit("ACADEMIA"))
            .when(desc.str.contains(_P_ESCOLA))
            .then(pl.lit("ESCOLA"))
            .when(desc.str.contains(_P_SAUDE))
            .then(pl.lit("SAUDE"))
            .when(desc.str.contains(_P_BROKER))
            .then(pl.lit("CORRETORA"))
            .when(desc.str.contains(_P_SUPERMERCADO))
            .then(pl.lit("SUPERMERCADO"))
            .when(desc.str.contains(_P_RESTAURANTE))
            .then(pl.lit("RESTAURANTE"))
            .when(desc.str.contains(_P_STREAMING))
            .then(pl.lit("STREAMING"))
            .when(desc.str.contains(_P_COWORKING))
            .then(pl.lit("COWORKING"))
            .otherwise(pl.lit(None))
        )

        return df.with_columns(expr.alias("merchant_category_l2"))

    def _add_merchant_category_l1(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Categoria L1 canônica derivada do merchant_category_l2.

        Usa _L2_TO_L1 como fonte única de verdade — não duplicar o mapeamento inline.
        Mantém SUPERMERCADO e FARMACIA separados de ALIMENTACAO para preservar a
        granularidade dos cashback_categories em knowledge_cards.json.
        """
        if "merchant_category_l1" in df.columns:
            return df
        if "merchant_category_l2" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_category_l1"))

        l2 = pl.col("merchant_category_l2")
        expr = pl.lit(None).cast(pl.Utf8)
        for l2_val, l1_val in _L2_TO_L1.items():
            expr = pl.when(l2 == l2_val).then(pl.lit(l1_val)).otherwise(expr)

        return df.with_columns(expr.alias("merchant_category_l1"))

    def _add_category_canonical(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normaliza a categoria raw do banco (campo `category`) para formato canônico:
        lowercase, sem acento, sem espaço extra — alinhado com knowledge_cards.json.

        Ex: "Alimentação" → "alimentacao", "Saúde" → "saude", None → "outros".

        Quando merchant_category_l1 está disponível e a categoria raw é ausente/genérica
        ("Outros", None), usa o L1 como fallback para máxima cobertura.
        """
        if "category_canonical" in df.columns:
            return df

        if "category" not in df.columns:
            # Sem coluna raw: tenta usar merchant_category_l1 como proxy
            if "merchant_category_l1" in df.columns:
                return df.with_columns(
                    pl.col("merchant_category_l1").fill_null(CAT_OUTROS).alias("category_canonical")
                )
            return df.with_columns(pl.lit(CAT_OUTROS).alias("category_canonical"))

        # Passo 1: normalizar texto — lowercase + remover acentos comuns do português
        normalized = (
            pl.col("category")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .str.replace_all("á|â|ã", "a")
            .str.replace_all("é|ê", "e")
            .str.replace_all("í", "i")
            .str.replace_all("ó|ô|õ", "o")
            .str.replace_all("ú|ü", "u")
            .str.replace_all("ç", "c")
            .str.strip_chars()
            .fill_null(CAT_OUTROS)
        )

        # Passo 2: mapear aliases conhecidos → valor canônico
        # "restaurante" e "refeição" → alimentacao; "saúde e bem-estar" → saude; etc.
        canonical = (
            pl.when(normalized.is_in(["restaurante", "refeicao", "refeição"]))
            .then(pl.lit(CAT_ALIMENTACAO))
            .when(normalized.is_in(["farmacia", "farmácia", "drogaria"]))
            .then(pl.lit(CAT_FARMACIA))
            .when(normalized.is_in(["saude e bem-estar", "saúde e bem-estar", "bem-estar"]))
            .then(pl.lit(CAT_SAUDE))
            .when(normalized.is_in(["turismo", "turismo e viagem", "hotel"]))
            .then(pl.lit(CAT_VIAGEM))
            .when(normalized.is_in(["entretenimento", "diversao", "diversão"]))
            .then(pl.lit(CAT_LAZER))
            .when(normalized.is_in(["investimentos", "aplicacao", "aplicação"]))
            .then(pl.lit(CAT_FINANCAS))
            .otherwise(normalized)
        )

        # Passo 3: quando raw category é genérica ("outros"), prefere merchant_category_l1
        if "merchant_category_l1" in df.columns:
            canonical = (
                pl.when((canonical == CAT_OUTROS) & pl.col("merchant_category_l1").is_not_null())
                .then(pl.col("merchant_category_l1"))
                .otherwise(canonical)
            )

        return df.with_columns(canonical.alias("category_canonical"))

    def _add_merchant_normalized(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Nome do merchant limpo de ruído de pagamento.

        Remove prefixos de meio de pagamento ("PG*", "PAGAMENTO PIX", "TED "),
        asteriscos intermediários, sufixos ".COM" e códigos numéricos longos.
        Resultado em uppercase para consistência com os demais campos de texto.

        Útil para contagem de merchants distintos no EvidenceScore: sem isso
        "PG*SPOTIFY" e "SPOTIFY.COM" seriam contados como merchants diferentes.
        """
        if "merchant_normalized" in df.columns:
            return df
        if "description" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_normalized"))

        desc = pl.col("description").str.to_uppercase()

        normalized = (
            desc
            # Prefixos de pagamento no início.
            # PGT?O?\* cobre variantes: PG*, PGT*, PGTO* (ex: "PG*SPOTIFY", "PGTO*AMAZON")
            .str.replace_all(
                r"^(PGT?O?\*|PAG(?:AMENTO)?\s+(?:PIX\s+)?(?:ENVIADO\s+)?|PIX\s+(?:ENVIADO\s+)?|TED\s+|DOC\s+)",
                "",
            )
            # Separadores com asterisco → espaço único
            .str.replace_all(r"\s*\*\s*", " ")
            # Sufixo .COM
            .str.replace_all(r"\.COM\b", "")
            # Códigos numéricos longos no final (≥ 6 dígitos)
            .str.replace_all(r"\s+\d{6,}.*$", "")
            # Ruído de tipo de transação no final
            .str.replace_all(r"\s+(COMPRA|DEBITO|CREDITO|PGMT|LOJA\s+\d+)$", "")
            .str.strip_chars()
        )

        return df.with_columns(normalized.alias("merchant_normalized"))

    def _add_merchant_id(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        ID canônico estável por merchant — colapsa aliases do mesmo negócio.

        "PG*SPOTIFY", "SPOTIFY.COM", "SPOTIFY BRASIL" → merchant_id = "spotify"
        "UBER EATS COMPRA" → "uber_eats";  "UBER CORRIDA" → "uber"

        Para merchants fora da tabela de aliases (_MERCHANT_ALIASES), aplica
        normalização genérica: lowercase, remoção de sufixos legais, slugify.

        Depende de merchant_normalized (adicionado por _add_merchant_normalized).
        """
        if "merchant_id" in df.columns:
            return df
        if "merchant_normalized" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_id"))

        m = pl.col("merchant_normalized")  # uppercase, sem prefixo de pagamento

        # Fallback genérico: slugify para merchants não cobertos pela tabela
        general_fallback: pl.Expr = (
            m.str.to_lowercase()
            .str.replace_all(
                r"\s+(brasil|ltda|s\.?a\.?|s/a|eireli|me|epp|filial|matriz|loja\s*\d*)\s*$",
                "",
            )
            .str.replace_all(r"[^a-z0-9 ]+", " ")
            .str.strip_chars()
            .str.replace_all(r"\s+", "_")
            .str.slice(0, 40)
        )

        # Constrói when/then/otherwise a partir da tabela de aliases.
        # reversed() garante que o primeiro alias na lista tenha maior prioridade.
        expr: pl.Expr = general_fallback
        for pattern, mid in reversed(_MERCHANT_ALIASES):
            expr = pl.when(m.str.contains(pattern)).then(pl.lit(mid)).otherwise(expr)

        # Propaga null: sem description → sem merchant_id
        expr = pl.when(m.is_null()).then(pl.lit(None).cast(pl.Utf8)).otherwise(expr)

        return df.with_columns(expr.alias("merchant_id"))

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
        Adiciona day_of_week (ISO 1=Segunda…7=Domingo) e is_weekend.

        Polars dt.weekday() segue ISO 8601: 1=Segunda, 6=Sábado, 7=Domingo.
        NÃO é a convenção Python (0=Segunda…6=Domingo).

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
                (pl.col("day_of_week") >= 6).alias("is_weekend"),  # 6=Sábado, 7=Domingo
            )

        return df
