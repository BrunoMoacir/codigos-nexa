"""
app/etl/ingestor.py - Transforma JSON → DataFrame limpo (Polars)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
import polars as pl

from app.core.schemas.enums import DataStatus
from app.core.schemas.transaction import TransactionWebhook
from app.forecast.etl.bank_strategy import get_bank_strategy
from app.forecast.etl.dedup.base import DedupPolicy
from app.forecast.etl.dedup.default import DefaultDedupPolicy
from app.forecast.etl.text_normalizer import canonical_key_expr

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: MÉTRICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class QualityMetrics:
    total_records: int
    duplicates_removed: int
    records_after_dedup: int
    quality_score: float
    processing_time_ms: float

    trusted_count: int = 0
    degraded_count: int = 0
    untrusted_count: int = 0
    inserted_rows: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INGESTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TransactionIngestor:

    def __init__(self, dedup_policy: DedupPolicy | None = None):
        """
        Inicializa o TransactionIngestor.
        (Removida a dependência legacy do DuckDB)

        Args:
            dedup_policy: política de deduplicação. Default: DefaultDedupPolicy
                (dedup_hash composto conta+data+valor+descrição).
        """
        self.logger = logging.getLogger(__name__)
        self.dedup_policy = dedup_policy or DefaultDedupPolicy()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PROCESS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def process(
        self,
        transactions: list[TransactionWebhook]
    ) -> tuple[pl.DataFrame, QualityMetrics]:

        if not transactions:
            raise ValueError("Lista de transações vazia")

        start_time = datetime.now()

        # 1. JSON → DataFrame
        df = self._to_dataframe(transactions)

        # 2. Deduplicação semântica (dedup_hash já vem calculado do schema).
        #    Cobre reentrega de webhook e reprocessamento de item pela Pluggy,
        #    que gera IDs novos para a MESMA transação — caso em que o upsert
        #    por transaction_id não protege.
        df, duplicates_removed = self.dedup_policy.apply(df)
        if duplicates_removed:
            self.logger.info(
                "Ingestor: %s duplicatas removidas de %s registros",
                duplicates_removed,
                len(transactions),
            )

        # 3. Normalização de texto
        df = self._normalize_texts(df)

        # 4. BankStrategy
        df = self._apply_bank_strategies(df)

        # 5. Chave canônica de estabelecimento (une o que cada banco escreve
        #    do seu jeito)
        df = self._canonicalize_merchant(df)

        # 6. Conversão de tipos (antes da estimativa: cumsum precisa de Float64)
        df = self._convert_types(df)

        # 7. Saldo estimado por cumsum onde o banco não mandou, e só então o
        #    downgrade de qualidade POR LINHA — lacuna preenchida por
        #    estimativa deixa de contar como lacuna
        df = self._estimate_balances(df)
        df = self._apply_row_quality(df)

        # 8. Enriquecimento
        df = self._enrich_columns(df)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        metrics = QualityMetrics(
            total_records=len(transactions),
            duplicates_removed=duplicates_removed,
            records_after_dedup=len(df),
            quality_score=1.0, # Assumindo 100% de qualidade pré-validação
            processing_time_ms=processing_time,
            trusted_count=df.filter(pl.col("data_status") == "TRUSTED").height if "data_status" in df.columns else len(df),
            degraded_count=df.filter(pl.col("data_status") == "DEGRADED").height if "data_status" in df.columns else 0,
            untrusted_count=df.filter(pl.col("data_status") == "UNTRUSTED").height if "data_status" in df.columns else 0,
            inserted_rows=0 # Load agora é feito no postgres no pipeline principal
        )

        return df, metrics

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _to_dataframe(self, transactions: list[TransactionWebhook]) -> pl.DataFrame:
        return pl.DataFrame([tx.model_dump() for tx in transactions])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2 — NORMALIZAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _normalize_texts(self, df: pl.DataFrame) -> pl.DataFrame:
        for col in ["description", "merchant"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col)
                    .cast(pl.String)
                    .fill_null("")
                    .str.strip_chars()
                    .str.to_lowercase()
                    .alias(col)
                )
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3 — BANK STRATEGY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _apply_bank_strategies(self, df: pl.DataFrame) -> pl.DataFrame:
        banks = df.select("institution_id").unique().to_series().to_list()
        processed = []

        for bank_id in banks:
            bank_df = df.filter(pl.col("institution_id") == bank_id)
            try:
                strategy = get_bank_strategy(bank_id)
                bank_df = strategy.normalize(bank_df)
                status = strategy.evaluate_quality(bank_df)
                bank_df = bank_df.with_columns(
                    pl.lit(status.value).alias("data_status")
                )
            except Exception:
                bank_df = bank_df.with_columns(
                    pl.lit("UNTRUSTED").alias("data_status")
                )

            processed.append(bank_df)

        return pl.concat(processed, how="diagonal_relaxed")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5a — CHAVE CANÔNICA DE ESTABELECIMENTO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _canonicalize_merchant(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Cria `merchant_key`: a mesma compra escrita por bancos diferentes
        (e por meses diferentes) converge para a mesma chave.

        Deriva do merchant quando o banco mandou um — é o dado mais limpo —
        e cai para a descrição quando não mandou. A descrição original NÃO é
        tocada: quem precisa do texto cru (extrato, auditoria) continua tendo.

        Consumidores: RecurringDetector (agrupa assinatura por chave, não por
        descrição, que muda de mês em mês em Bradesco/Itaú) e
        TransactionClassifier (classifica texto limpo, não ruído de adquirente).
        """
        base = pl.col("description")
        if "merchant" in df.columns:
            base = (
                pl.when(pl.col("merchant").cast(pl.String).fill_null("").str.len_chars() > 0)
                .then(pl.col("merchant"))
                .otherwise(pl.col("description"))
            )

        df = df.with_columns(canonical_key_expr(base).alias("merchant_key"))

        # merchant vazio herda a chave — melhor "netflix" do que nada
        if "merchant" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("merchant").cast(pl.String).fill_null("").str.len_chars() == 0)
                .then(pl.col("merchant_key"))
                .otherwise(pl.col("merchant"))
                .alias("merchant")
            )

        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7a — SALDO ESTIMADO (cumsum)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _estimate_balances(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Preenche saldo faltante por soma acumulada, ancorada em qualquer
        saldo real da mesma conta.

        Invariante: saldo_i = saldo_j + (soma dos amounts entre j e i). Com
        S = cumsum(amount) na ordem cronológica da conta, (balance - S) é
        constante entre âncoras — forward/backward fill dessa constante
        reconstrói o saldo de todas as linhas, antes e depois da âncora.

        `balance_estimated` marca o que é derivado: o consumidor decide se
        confia. Conta SEM nenhuma âncora fica com saldo nulo mesmo — estimar
        do nada seria inventar dinheiro.
        """
        if "balance" not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("balance"))

        faltantes = df.filter(pl.col("balance").is_null()).height
        if faltantes == 0:
            return df.with_columns(pl.lit(False).alias("balance_estimated"))

        df = (
            df.with_row_index("_ordem_original")
            .sort(["account_id", "transaction_date", "_ordem_original"])
            .with_columns(
                pl.col("amount").cum_sum().over("account_id").alias("_soma_acum")
            )
            .with_columns(
                (pl.col("balance") - pl.col("_soma_acum"))
                .forward_fill()
                .backward_fill()
                .over("account_id")
                .alias("_base_conta")
            )
            .with_columns(
                pl.col("balance").is_null()
                .and_(pl.col("_base_conta").is_not_null())
                .alias("balance_estimated"),
                pl.coalesce([
                    pl.col("balance"),
                    pl.col("_base_conta") + pl.col("_soma_acum"),
                ]).alias("balance"),
            )
            .sort("_ordem_original")
            .drop("_ordem_original", "_soma_acum", "_base_conta")
        )

        estimados = df.filter(pl.col("balance_estimated")).height
        if estimados:
            self.logger.info(
                "Ingestor: %s de %s saldos faltantes estimados por cumsum",
                estimados, faltantes,
            )
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7b — QUALIDADE POR LINHA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _apply_row_quality(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        A BankStrategy dá o TETO de confiança do banco (tier); aqui cada linha
        é rebaixada pelo que falta NELA.

        Antes o veredito era só do lote: um saldo nulo em 50 transações
        marcava as 50 como DEGRADED, e o Nubank saía TRUSTED mesmo com a
        descrição inteira vazia. Só rebaixa — nunca promove acima do teto.

        Roda DEPOIS da estimativa de saldo: lacuna preenchida por cumsum não
        é mais lacuna (a linha carrega balance_estimated=True para quem
        precisar distinguir). Saldo nulo aqui significa conta sem âncora
        nenhuma — aí sim, DEGRADED.
        """
        if "data_status" not in df.columns:
            return df

        incompleta = pl.col("description").cast(pl.String).fill_null("").str.len_chars() == 0
        if "balance" in df.columns:
            incompleta = incompleta | pl.col("balance").is_null()

        return df.with_columns(
            pl.when((pl.col("data_status") == DataStatus.TRUSTED.value) & incompleta)
            .then(pl.lit(DataStatus.DEGRADED.value))
            .otherwise(pl.col("data_status"))
            .alias("data_status")
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 6 — TIPOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _convert_types(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns(pl.col("amount").cast(pl.Float64))
        if "balance" in df.columns:
            df = df.with_columns(pl.col("balance").cast(pl.Float64))
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5 — ENRIQUECIMENTO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns([
            pl.col("transaction_date").dt.month().alias("month"),
            pl.col("transaction_date").dt.weekday().alias("day_of_week"),
            pl.when(pl.col("amount") < 0)
              .then(pl.lit("DEBIT"))
              .otherwise(pl.lit("CREDIT"))
              .alias("transaction_type")
        ])
