"""
app/etl/ingestor.py - Transforma JSON → DataFrame limpo (Polars)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Recebe lista de TransactionWebhook (já validados pelo Pydantic) e:
1. Converte para DataFrame Polars
2. Deduplica transações (via dedup_hash)
3. Normaliza textos (lowercase, sem acentos)
4. Converte tipos (Decimal → Float64, datetime → consistent)
5. Enriquece com colunas calculadas (month, day_of_week, etc)
6. Calcula métricas de qualidade

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE POLARS E NÃO PANDAS?                                         ║
╚══════════════════════════════════════════════════════════════════════╝

Polars é 10-100x mais rápido que pandas porque:
- Escrito em Rust (compilado, não interpretado)
- Paralelização automática (usa todos os cores da CPU)
- Lazy evaluation (otimiza queries antes de executar)
- Menos uso de memória (tipos nativos, não objetos Python)

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO DE DADOS                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

ENTRADA:  list[TransactionWebhook] (validados pelo Pydantic)
           ↓
PROCESSO: 1. JSON → DataFrame
           2. Deduplica
           3. Normaliza textos
           4. Converte tipos
           5. Enriquece colunas
           6. Calcula métricas
           ↓
SAÍDA:    pl.DataFrame limpo + QualityMetrics

╔══════════════════════════════════════════════════════════════════════╗
║ EXEMPLO DE USO                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

from app.etl import TransactionIngestor
from app.schemas.transaction import TransactionWebhook

# 1. Recebe transações do webhook (já validadas)
transactions = [
    TransactionWebhook(
        transaction_id="txn_1",
        amount=-50.00,
        transaction_date="2024-01-20T10:00:00Z",
        ...
    )
]

# 2. Processa
ingestor = TransactionIngestor()
clean_df, metrics = ingestor.process(transactions)

# 3. Resultado:
# clean_df: pl.DataFrame com colunas normalizadas
# metrics: QualityMetrics (total_records, duplicates_removed, etc)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import polars as pl

from app.schemas.transaction import TransactionWebhook

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
    
    Usado para:
        - Debugging (quantas transações foram processadas?)
        - Alertas (muitas duplicatas = problema?)
        - Auditoria (registrar no banco)
    
    Attributes:
        total_records: Total de transações recebidas
        duplicates_removed: Quantas duplicatas foram removidas
        records_after_dedup: Transações únicas restantes
        quality_score: Score 0.0-1.0 (1.0 = perfeito, sem duplicatas)
        processing_time_ms: Tempo de processamento em milissegundos
    """
    total_records: int
    duplicates_removed: int
    records_after_dedup: int
    quality_score: float  # 0.0 - 1.0
    processing_time_ms: float


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASSE PRINCIPAL: TRANSACTION INGESTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TransactionIngestor:
    """
    Processa transações validadas (Pydantic) → DataFrame limpo (Polars).
    
    Pipeline de 6 passos:
        1. JSON → DataFrame
        2. Deduplica (dedup_hash)
        3. Normaliza textos
        4. Converte tipos
        5. Enriquece colunas
        6. Calcula métricas
    
    Responsabilidades:
        ✅ Remover ruído antes de análise
        ✅ Garantir tipos corretos (evita bugs downstream)
        ✅ Performance (Polars é 10-100x mais rápido que pandas)
        ✅ Consistência (mesma limpeza para todos os bancos)
    
    NÃO faz:
        ❌ Validação estrutural (Pydantic já fez)
        ❌ Classificação de categoria (classifier.py faz)
        ❌ Detecção de recorrências (recurring_detector.py faz)
    """
    
    def __init__(self):
        """
        Inicializa o ingestor.
        
        Por enquanto não precisa de configuração, mas no futuro
        pode receber parâmetros como:
            - normalize_case: bool (default True)
            - remove_accents: bool (default True)
            - dedup_strategy: "hash" | "sql" (default "hash")
        """
        logger.info("TransactionIngestor inicializado")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODO PRINCIPAL: PROCESS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def process(
        self,
        transactions: list[TransactionWebhook]
    ) -> tuple[pl.DataFrame, QualityMetrics]:
        """
        Processa lista de transações → DataFrame limpo.
        
        Args:
            transactions: Lista de TransactionWebhook validadas pelo Pydantic
        
        Returns:
            Tupla com:
                - pl.DataFrame: DataFrame limpo e normalizado
                - QualityMetrics: Métricas do processamento
        
        Raises:
            ValueError: Se transactions estiver vazia
            TypeError: Se transactions não for lista de TransactionWebhook
        
        Example:
            >>> ingestor = TransactionIngestor()
            >>> clean_df, metrics = ingestor.process(transactions)
            >>> print(metrics.quality_score)  # 0.95 (95% qualidade)
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÃO DE ENTRADA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if not transactions:
            raise ValueError("Lista de transações está vazia")
        
        if not isinstance(transactions, list):
            raise TypeError("transactions deve ser uma lista")
        
        if not all(isinstance(tx, TransactionWebhook) for tx in transactions):
            raise TypeError("Todos os itens devem ser TransactionWebhook")
        
        # Marca início do processamento (para calcular tempo)
        start_time = datetime.now()
        
        logger.info(
            "Iniciando processamento ETL",
            extra={"total_transactions": len(transactions)}
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 1: JSON → DATAFRAME
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = self._to_dataframe(transactions)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 2: DEDUPLICA (dedup_hash)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df, duplicates_removed = self._deduplicate(df)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 3: NORMALIZA TEXTOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = self._normalize_texts(df)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 4: CONVERTE TIPOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = self._convert_types(df)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 5: ENRIQUECE COLUNAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = self._enrich_columns(df)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PASSO 6: CALCULA MÉTRICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
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
    # MÉTODOS PRIVADOS (PASSOS DO PIPELINE)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _to_dataframe(self, transactions: list[TransactionWebhook]) -> pl.DataFrame:
        """
        PASSO 1: Converte lista de TransactionWebhook → DataFrame Polars.
        
        Process:
            1. Serializa cada TransactionWebhook para dict
            2. Cria DataFrame Polars a partir da lista de dicts
        
        Args:
            transactions: Lista de TransactionWebhook
        
        Returns:
            pl.DataFrame com as mesmas colunas do TransactionWebhook
        
        Notes:
            - model_dump() serializa Pydantic → dict
            - Polars infere tipos automaticamente dos dicts
            - datetime já vem como datetime (não como string)
        """
        # Serializa cada TransactionWebhook para dict
        # model_dump() é método do Pydantic que converte para dict Python
        raw_dicts = [tx.model_dump() for tx in transactions]
        
        # Cria DataFrame Polars
        # Polars infere tipos automaticamente:
        # - str → pl.Utf8
        # - int → pl.Int64
        # - float → pl.Float64
        # - datetime → pl.Datetime
        df = pl.DataFrame(raw_dicts)
        
        logger.debug(
            "DataFrame criado",
            extra={"shape": df.shape, "columns": df.columns}
        )
        
        return df
    
    
    def _deduplicate(self, df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
        """
        PASSO 2: Remove duplicatas baseado em dedup_hash.
        
        Estratégia:
            - dedup_hash é calculado no Pydantic (transaction.py)
            - Hash baseado em: account_id + date + amount + description[:20]
            - Keep "first" = mantém a primeira ocorrência
        
        Args:
            df: DataFrame com coluna 'dedup_hash'
        
        Returns:
            Tupla com:
                - DataFrame sem duplicatas
                - Número de duplicatas removidas
        
        Example:
            >>> df = pl.DataFrame({
            ...     "dedup_hash": ["hash1", "hash1", "hash2"],
            ...     "amount": [-50, -50, -100]
            ... })
            >>> df_clean, removed = self._deduplicate(df)
            >>> removed
            1  # Uma duplicata removida
        """
        # Conta registros antes da deduplicação
        before_count = len(df)
        
        # Remove duplicatas
        # subset=["dedup_hash"]: coluna para comparação
        # keep="first": mantém primeira ocorrência, remove demais
        df = df.unique(subset=["dedup_hash"], keep="first")
        
        # Conta registros depois
        after_count = len(df)
        
        # Calcula quantas foram removidas
        duplicates_removed = before_count - after_count
        
        if duplicates_removed > 0:
            logger.warning(
                "Duplicatas removidas",
                extra={"duplicates_removed": duplicates_removed}
            )
        
        return df, duplicates_removed
    
    
    def _normalize_texts(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        PASSO 3: Normaliza colunas de texto (lowercase, strip).
        
        Colunas normalizadas:
            - description: Descrição da transação
            - merchant: Nome do estabelecimento
        
        Normalizações aplicadas:
            1. .str.strip() → Remove espaços no início/fim
            2. .str.to_lowercase() → Tudo minúsculo
        
        Por que normalizar?
            - Facilita busca ("UBER" = "uber" = "Uber")
            - Melhora performance de ML (menos variações)
            - Consistência entre bancos
        
        Args:
            df: DataFrame com colunas de texto
        
        Returns:
            DataFrame com textos normalizados
        
        Example:
            ANTES: description="  PAG UBER VIAGEM  "
            DEPOIS: description="pag uber viagem"
        """
        # Lista de colunas de texto para normalizar
        text_columns = ["description", "merchant"]
        
        # Para cada coluna de texto no DataFrame
        for col in text_columns:
            if col in df.columns:
                # Aplica normalização:
                # 1. strip() remove espaços extras
                # 2. to_lowercase() converte para minúsculo
                df = df.with_columns(
                    pl.col(col)
                    .str.strip()
                    .str.to_lowercase()
                    .alias(col)  # Mantém o mesmo nome da coluna
                )
        
        logger.debug("Textos normalizados", extra={"columns": text_columns})
        
        return df
    
    
    def _convert_types(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        PASSO 4: Converte tipos para formato consistente.
        
        Conversões:
            - amount: Decimal → Float64 (JSON não suporta Decimal)
            - balance: Decimal → Float64
            - transaction_date: já é datetime (Pydantic converteu)
        
        Por que converter?
            - Float64 é nativo do Polars (mais rápido)
            - JSON não serializa Decimal (precisa ser float)
            - Cálculos matemáticos usam float, não Decimal
        
        Args:
            df: DataFrame com tipos mistos
        
        Returns:
            DataFrame com tipos consistentes
        
        Notes:
            - Pydantic usa Decimal para precisão (evita 0.1 + 0.2 = 0.30000000004)
            - Polars usa Float64 para performance
            - Perda de precisão é aceitável em análises (não em cálculos críticos)
        """
        # Converte amount (Decimal → Float64)
        # .cast(pl.Float64) converte tipo da coluna
        df = df.with_columns(pl.col("amount").cast(pl.Float64))
        
        # Converte balance (pode ser None, então usa fill_null antes)
        if "balance" in df.columns:
            df = df.with_columns(pl.col("balance").cast(pl.Float64))
        
        logger.debug("Tipos convertidos para Float64")
        
        return df
    
    
    def _enrich_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        PASSO 5: Adiciona colunas calculadas (features engineering).
        
        Colunas criadas:
            - month: Mês da transação (1-12)
            - day_of_week: Dia da semana (1=Segunda, 7=Domingo)
            - transaction_type: "DEBIT" ou "CREDIT" (baseado em amount)
        
        Por que enriquecer?
            - month: Análise de sazonalidade (gastos em dezembro > janeiro)
            - day_of_week: Padrões de consumo (fim de semana vs dias úteis)
            - transaction_type: Facilita filtros (só débitos, só créditos)
        
        Args:
            df: DataFrame limpo
        
        Returns:
            DataFrame com colunas adicionais
        
        Example:
            ANTES:
            ┌──────────┬────────────────────┐
            │ amount   │ transaction_date   │
            ├──────────┼────────────────────┤
            │ -50.00   │ 2024-01-15 10:00   │
            └──────────┴────────────────────┘
            
            DEPOIS:
            ┌──────────┬────────────────────┬───────┬─────────────┬──────────────────┐
            │ amount   │ transaction_date   │ month │ day_of_week │ transaction_type │
            ├──────────┼────────────────────┼───────┼─────────────┼──────────────────┤
            │ -50.00   │ 2024-01-15 10:00   │ 1     │ 1 (seg)     │ DEBIT            │
            └──────────┴────────────────────┴───────┴─────────────┴──────────────────┘
        """
        df = df.with_columns([
            # Extrai mês da data (1-12)
            # .dt.month() é método do Polars para datetime
            pl.col("transaction_date").dt.month().alias("month"),
            
            # Extrai dia da semana (1=Segunda, 7=Domingo)
            # .dt.weekday() retorna int 1-7
            pl.col("transaction_date").dt.weekday().alias("day_of_week"),
            
            # Classifica como DEBIT ou CREDIT baseado no sinal
            # pl.when() é if-else do Polars
            # amount < 0 → DEBIT (débito)
            # amount >= 0 → CREDIT (crédito)
            pl.when(pl.col("amount") < 0)
              .then(pl.lit("DEBIT"))
              .otherwise(pl.lit("CREDIT"))
              .alias("transaction_type")
        ])
        
        logger.debug("Colunas enriquecidas adicionadas")
        
        return df
    
    
    def _calculate_metrics(
        self,
        total_records: int,
        duplicates_removed: int,
        records_after_dedup: int,
        processing_time_ms: float
    ) -> QualityMetrics:
        """
        PASSO 6: Calcula métricas de qualidade do processamento.
        
        Métricas:
            - quality_score: 0.0-1.0 (quanto menos duplicatas, melhor)
              Fórmula: (records_after_dedup / total_records)
              Exemplo: 95 únicos / 100 total = 0.95 (95% qualidade)
        
        Args:
            total_records: Total de transações recebidas
            duplicates_removed: Quantas duplicatas foram removidas
            records_after_dedup: Transações únicas restantes
            processing_time_ms: Tempo de processamento em ms
        
        Returns:
            QualityMetrics com todos os campos preenchidos
        
        Notes:
            - quality_score = 1.0 → perfeito (0 duplicatas)
            - quality_score < 0.9 → alerta (muitas duplicatas)
            - Métricas podem ser salvas no Postgres para auditoria
        """
        # Calcula quality score (0.0 - 1.0)
        # Se não houver registros, score = 0
        if total_records > 0:
            quality_score = records_after_dedup / total_records
        else:
            quality_score = 0.0
        
        metrics = QualityMetrics(
            total_records=total_records,
            duplicates_removed=duplicates_removed,
            records_after_dedup=records_after_dedup,
            quality_score=quality_score,
            processing_time_ms=processing_time_ms
        )
        
        return metrics