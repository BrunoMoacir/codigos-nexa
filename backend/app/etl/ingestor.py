"""
app/etl/ingestor.py - Transforma JSON → DataFrame limpo (Polars)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Recebe lista de TransactionWebhook (já validados pelo Pydantic) e:
1. Converte para DataFrame Polars
2. Deduplica transações (via dedup_hash)
3. Normaliza textos (trim + lowercase)
4. Converte tipos (Decimal → Float64, datetime consistente)
5. Enriquece com colunas calculadas (month, day_of_week, etc)
6. Calcula métricas de qualidade
7. ✅ NOVO: Aplica BankStrategy (normalização específica por banco)
8. ✅ NOVO: Avalia qualidade (data_status: TRUSTED/DEGRADED/UNTRUSTED)


╔══════════════════════════════════════════════════════════════════════╗
║ MUDANÇAS COM BANKSTRATEGY                                            ║
╚══════════════════════════════════════════════════════════════════════╝

ANTES:
  JSON → DataFrame → Deduplica → Normaliza Texto → Enriquece

DEPOIS:
  JSON → DataFrame → Deduplica → ✅ BankStrategy → Normaliza Texto → Enriquece
                                      ↓
                          (normaliza POR BANCO + avalia qualidade)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import polars as pl

from app.schemas.transaction import TransactionWebhook
from app.etl.bank_strategy import get_bank_strategy  # ✅ NOVO

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO DE LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: MÉTRICAS DE QUALIDADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class QualityMetrics:
    """
    Métricas de qualidade do processamento ETL.
    """
    total_records: int
    duplicates_removed: int
    records_after_dedup: int
    quality_score: float
    processing_time_ms: float

    # ✅ NOVO: Distribuição de qualidade por banco
    trusted_count: int = 0
    degraded_count: int = 0
    untrusted_count: int = 0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASSE PRINCIPAL: TRANSACTION INGESTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TransactionIngestor:
    """
    Processa transações validadas (Pydantic) → DataFrame limpo (Polars).
    """

    def __init__(self):
        logger.info("TransactionIngestor inicializado")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODO PRINCIPAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def process(
        self,
        transactions: list[TransactionWebhook]
    ) -> tuple[pl.DataFrame, QualityMetrics]:

        if not transactions:
            raise ValueError("Lista de transações está vazia")

        if not isinstance(transactions, list):
            raise TypeError("transactions deve ser uma lista")

        if not all(isinstance(tx, TransactionWebhook) for tx in transactions):
            raise TypeError("Todos os itens devem ser TransactionWebhook")

        start_time = datetime.now()

        logger.info(
            "Iniciando processamento ETL",
            extra={"total_transactions": len(transactions)}
        )

        # PASSO 1: JSON → DataFrame
        df = self._to_dataframe(transactions)

        # PASSO 2: Deduplicação
        df, duplicates_removed = self._deduplicate(df)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✅ PASSO 3: BANKSTRATEGY (NOVO)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        df = self._apply_bank_strategies(df)

        # PASSO 4: Normalização de textos
        df = self._normalize_texts(df)

        # PASSO 5: Conversão de tipos
        df = self._convert_types(df)

        # PASSO 6: Enriquecimento
        df = self._enrich_columns(df)

        # PASSO 7: Métricas
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        metrics = self._calculate_metrics(
            total_records=len(transactions),
            duplicates_removed=duplicates_removed,
            records_after_dedup=len(df),
            processing_time_ms=processing_time
        )

        logger.info(
            "Processamento ETL concluído",
            extra={
                "total_records": metrics.total_records,
                "duplicates_removed": metrics.duplicates_removed,
                "quality_score": metrics.quality_score,
                "processing_time_ms": metrics.processing_time_ms
            }
        )

        return df, metrics

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1: JSON → DataFrame
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _to_dataframe(self, transactions: list[TransactionWebhook]) -> pl.DataFrame:
        raw_dicts = [tx.model_dump() for tx in transactions]
        df = pl.DataFrame(raw_dicts)

        logger.debug("DataFrame criado", extra={"shape": df.shape})
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2: Deduplicação
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _deduplicate(self, df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
        before = len(df)
        df = df.unique(subset=["dedup_hash"], keep="first")
        removed = before - len(df)

        if removed > 0:
            logger.warning("Duplicatas removidas", extra={"count": removed})

        return df, removed
    
    #  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ✅ PASSO 3: BANKSTRATEGY (NOVO)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _apply_bank_strategies(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Aplica normalização específica por banco + avalia qualidade.
        
        ALGORITMO:
            1. Agrupa transações por institution_id
            2. Para cada banco:
               - Obtém strategy (get_bank_strategy)
               - Normaliza dados (strategy.normalize)
               - Avalia qualidade (strategy.evaluate_quality)
               - Adiciona coluna data_status
            3. Concatena todos DataFrames
        
        EXEMPLO:
            Input:
              ┌──────────────┬────────┬────────────────┐
              │ description  │ amount │ institution_id │
              ├──────────────┼────────┼────────────────┤
              │ UBER*VIAGEM  │ 50.00  │ itau           │  ← BUG: sinal errado
              │ uber trip    │ -45.00 │ nubank         │  ← OK
              └──────────────┴────────┴────────────────┘
            
            Output (após BankStrategy):
              ┌──────────────┬────────┬────────────────┬─────────────┐
              │ description  │ amount │ institution_id │ data_status │
              ├──────────────┼────────┼────────────────┼─────────────┤
              │ uber viagem  │ -50.00 │ itau           │ DEGRADED    │  ← Corrigido!
              │ uber trip    │ -45.00 │ nubank         │ TRUSTED     │  ← Mantido
              └──────────────┴────────┴────────────────┴─────────────┘
        """
        
        # Verifica se coluna institution_id existe
        if "institution_id" not in df.columns:
            logger.warning("institution_id não encontrado, pulando BankStrategy")
            # Adiciona data_status padrão
            return df.with_columns(pl.lit("UNKNOWN").alias("data_status"))
        
        # Agrupa por banco
        banks = df.select("institution_id").unique().to_series().to_list()
        
        logger.info(
            "Aplicando BankStrategy",
            extra={"banks": banks, "total_banks": len(banks)}
        )
        
        # Processa cada banco separadamente
        processed_dfs = []
        
        for bank_id in banks:
            # Filtra transações deste banco
            bank_df = df.filter(pl.col("institution_id") == bank_id)
            
            logger.debug(
                "Processando banco",
                extra={"bank_id": bank_id, "count": len(bank_df)}
            )
            
            try:
                # Obtém strategy do banco
                strategy = get_bank_strategy(bank_id)
                
                # NORMALIZA (correções específicas do banco)
                bank_df = strategy.normalize(bank_df)
                
                # AVALIA QUALIDADE (calcula data_status)
                data_status = strategy.evaluate_quality(bank_df)
                
                # Adiciona coluna data_status
                bank_df = bank_df.with_columns(
                    pl.lit(data_status.value).alias("data_status")
                )
                
                logger.info(
                    "Banco processado",
                    extra={
                        "bank_id": bank_id,
                        "strategy": strategy.__class__.__name__,
                        "tier": strategy.tier.value,
                        "data_status": data_status.value,
                        "count": len(bank_df)
                    }
                )
                
            except Exception as e:
                logger.error(
                    "Erro ao processar banco",
                    extra={"bank_id": bank_id, "error": str(e)},
                    exc_info=True
                )
                # Fallback: marca como UNTRUSTED
                bank_df = bank_df.with_columns(
                    pl.lit("UNTRUSTED").alias("data_status")
                )
            
            processed_dfs.append(bank_df)
        
        # Concatena todos DataFrames processados
        if not processed_dfs:
            logger.warning("Nenhum DataFrame processado")
            return df.with_columns(pl.lit("UNKNOWN").alias("data_status"))
        
        result_df = pl.concat(processed_dfs)
        
        logger.info(
            "BankStrategy aplicado",
            extra={"total_records": len(result_df)}
        )
        
        return result_df


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4 — NORMALIZAÇÃO (CORRIGIDO)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _normalize_texts(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normaliza colunas de texto usando API correta do Polars.

        IMPORTANTE:
        ❌ Polars NÃO possui `.str.strip()`
        ✅ O equivalente correto é `.str.trim()`

        Operações aplicadas:
            - trim(): remove espaços no início e fim
            - to_lowercase(): converte para minúsculas

        Benefícios:
            - Consistência entre bancos
            - Facilita busca e ML
            - Evita variações semânticas ("UBER" vs "uber")
        """

        text_columns = ["description", "merchant"]

        for col in text_columns:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col)
                    .cast(pl.String)
                    .fill_null("")  # Preenche nulos com string vazia
                    .str.strip_chars()          # remove espaços (Polars)
                    .str.to_lowercase()  # lowercase
                    .alias(col)
                )

        logger.debug("Textos normalizados", extra={"columns": text_columns})
        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5: Conversão de Tipos
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _convert_types(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns(pl.col("amount").cast(pl.Float64))

        if "balance" in df.columns:
            df = df.with_columns(pl.col("balance").cast(pl.Float64))

        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 6: Enriquecimento
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns([
            pl.col("transaction_date").dt.month().alias("month"),
            pl.col("transaction_date").dt.weekday().alias("day_of_week"),
            pl.when(pl.col("amount") < 0)
              .then(pl.lit("DEBIT"))
              .otherwise(pl.lit("CREDIT"))
              .alias("transaction_type")
        ])

        return df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7: Métricas de Qualidade
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _calculate_metrics(
        self,
        total_records: int,
        duplicates_removed: int,
        records_after_dedup: int,
        processing_time_ms: float
    ) -> QualityMetrics:

        quality_score = (
            records_after_dedup / total_records
            if total_records > 0 else 0.0
        )

        return QualityMetrics(
            total_records=total_records,
            duplicates_removed=duplicates_removed,
            records_after_dedup=records_after_dedup,
            quality_score=quality_score,
            processing_time_ms=processing_time_ms
        )
