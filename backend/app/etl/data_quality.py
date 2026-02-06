"""
app/etl/data_quality.py - Validador de Qualidade de Dados

RESPONSABILIDADE:
    Analisa qualidade global dos dados após ETL e calcula confidence score

VALIDAÇÕES:
    - Cobertura temporal (lacunas nos dados)
    - Anomalias (valores absurdos, duplicatas semânticas)
    - Consistência de saldo
    - Completude de campos

USAGE:
    validator = DataQualityValidator()
    report = validator.validate(df, period_days=30)
    print(report.overall_confidence)  # 0.85
"""

import logging
import polars as pl
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QualityLevel = Literal["EXCELLENT", "GOOD", "FAIR", "POOR"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class DataQualityReport:
    """
    Relatório de qualidade de dados.
    
    Attributes:
        overall_confidence: Score global de confiança (0.0-1.0)
        quality_level: EXCELLENT/GOOD/FAIR/POOR
        temporal_coverage: % de dias com dados (0.0-1.0)
        gap_count: Número de lacunas detectadas
        anomaly_count: Número de anomalias detectadas
        completeness_score: % de campos obrigatórios preenchidos
        balance_consistency: Score de consistência de saldo (0.0-1.0)
        issues: Lista de problemas detectados
        recommendations: Recomendações de ação
    
    Example:
        >>> report = DataQualityReport(
        ...     overall_confidence=0.85,
        ...     quality_level="GOOD",
        ...     temporal_coverage=0.90,
        ...     gap_count=3,
        ...     anomaly_count=1,
        ...     completeness_score=0.95,
        ...     balance_consistency=0.88,
        ...     issues=["Lacuna de 2 dias em Jan/2024"],
        ...     recommendations=["Considerar Shadow Invoice para preencher lacunas"]
        ... )
    """
    
    overall_confidence: float
    quality_level: QualityLevel
    temporal_coverage: float
    gap_count: int
    anomaly_count: int
    completeness_score: float
    balance_consistency: float
    issues: list[str]
    recommendations: list[str]
    
    def to_dict(self) -> dict:
        """Converte para dict (útil para JSON)."""
        return {
            "overall_confidence": self.overall_confidence,
            "quality_level": self.quality_level,
            "temporal_coverage": self.temporal_coverage,
            "gap_count": self.gap_count,
            "anomaly_count": self.anomaly_count,
            "completeness_score": self.completeness_score,
            "balance_consistency": self.balance_consistency,
            "issues": self.issues,
            "recommendations": self.recommendations
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: ANÁLISE DE COBERTURA TEMPORAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TemporalCoverageAnalysis:
    """
    Analisa cobertura temporal dos dados.
    
    Detecta lacunas (dias sem transações) e calcula score de cobertura.
    """
    
    @staticmethod
    def analyze(df: pl.DataFrame, period_days: int = 30) -> tuple[float, int, list[str]]:
        """
        Analisa cobertura temporal.
        
        Args:
            df: DataFrame com coluna 'transaction_date'
            period_days: Período de análise (dias)
        
        Returns:
            (coverage_score, gap_count, issues)
            
            coverage_score: % de dias com dados (0.0-1.0)
            gap_count: Número de lacunas detectadas
            issues: Lista de problemas detectados
        
        Example:
            >>> coverage, gaps, issues = TemporalCoverageAnalysis.analyze(df, 30)
            >>> print(f"Cobertura: {coverage:.1%}, Lacunas: {gaps}")
            Cobertura: 90.0%, Lacunas: 3
        """
        if df.is_empty() or "transaction_date" not in df.columns:
            return 0.0, 0, ["DataFrame vazio ou sem transaction_date"]
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: EXTRAIR DATAS ÚNICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Garantir que transaction_date é datetime
        if df.schema.get("transaction_date") != pl.Datetime:
            df = df.with_columns(
                pl.col("transaction_date").cast(pl.Datetime)
            )
        
        # Extrair datas únicas (truncar para dia)
        unique_dates = df.select(
            pl.col("transaction_date").dt.date().alias("date")
        ).unique().sort("date")
        
        if unique_dates.is_empty():
            return 0.0, 0, ["Nenhuma data válida encontrada"]
        
        dates = unique_dates["date"].to_list()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: CALCULAR PERÍODO DE ANÁLISE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        min_date = min(dates)
        max_date = max(dates)
        actual_days = (max_date - min_date).days + 1
        
        # Usar o menor entre período solicitado e período real
        analysis_days = min(period_days, actual_days)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: DETECTAR LACUNAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        gaps = []
        issues = []
        
        for i in range(len(dates) - 1):
            current_date = dates[i]
            next_date = dates[i + 1]
            gap_days = (next_date - current_date).days - 1
            
            # Lacuna de 2+ dias é problemática
            if gap_days >= 2:
                gaps.append((current_date, next_date, gap_days))
                issues.append(
                    f"Lacuna de {gap_days} dias entre {current_date} e {next_date}"
                )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: CALCULAR COBERTURA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Cobertura = dias com dados / dias esperados
        days_with_data = len(dates)
        coverage_score = days_with_data / analysis_days
        
        return coverage_score, len(gaps), issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: DETECTOR DE ANOMALIAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AnomalyDetector:
    """
    Detecta anomalias nos dados (outliers, valores absurdos).
    """
    
    @staticmethod
    def detect(df: pl.DataFrame) -> tuple[int, list[str]]:
        """
        Detecta anomalias nos dados.
        
        Args:
            df: DataFrame com coluna 'amount'
        
        Returns:
            (anomaly_count, issues)
        
        Anomalias detectadas:
            - Valores absurdos (>1M ou <-1M)
            - Duplicatas semânticas (mesma descrição, valor, dia)
            - Valores exatamente zero
        
        Example:
            >>> count, issues = AnomalyDetector.detect(df)
            >>> print(f"Anomalias: {count}")
            Anomalias: 2
        """
        if df.is_empty() or "amount" not in df.columns:
            return 0, ["DataFrame vazio ou sem amount"]
        
        issues = []
        anomaly_count = 0
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANOMALIA 1: Valores absurdos
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        MAX_AMOUNT = 1_000_000.0  # 1 milhão
        
        absurd_values = df.filter(
            (pl.col("amount").abs() > MAX_AMOUNT)
        )
        
        if absurd_values.height > 0:
            count = absurd_values.height
            anomaly_count += count
            issues.append(f"{count} transações com valores absurdos (>1M)")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANOMALIA 2: Valores zero
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        zero_values = df.filter(pl.col("amount") == 0.0)
        
        if zero_values.height > 0:
            count = zero_values.height
            anomaly_count += count
            issues.append(f"{count} transações com valor zero")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANOMALIA 3: Duplicatas semânticas (não pegas pelo dedup_hash)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Agrupa por (description, amount, date) e conta duplicatas
        if "description" in df.columns and "transaction_date" in df.columns:
            duplicates = df.group_by([
                "description", 
                "amount", 
                pl.col("transaction_date").dt.date().alias("date")
            ]).agg(
                pl.len().alias("count")
            ).filter(pl.col("count") > 1)
            
            if duplicates.height > 0:
                count = duplicates.height
                anomaly_count += count
                issues.append(
                    f"{count} possíveis duplicatas semânticas "
                    "(mesma descrição/valor/dia)"
                )
        
        return anomaly_count, issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN CLASS: DATA QUALITY VALIDATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DataQualityValidator:
    """
    Validador de qualidade de dados (pós-ETL).
    
    Analisa:
        - Cobertura temporal (lacunas)
        - Anomalias (outliers, duplicatas)
        - Completude de campos
        - Consistência de saldo
    
    Example:
        >>> validator = DataQualityValidator()
        >>> report = validator.validate(df, period_days=30)
        >>> 
        >>> print(f"Confiança: {report.overall_confidence:.1%}")
        Confiança: 85.0%
        >>> 
        >>> print(f"Qualidade: {report.quality_level}")
        Qualidade: GOOD
    """
    
    def __init__(self):
        """Inicializa validador."""
        self.logger = logging.getLogger(__name__)
    
    def validate(
        self, 
        df: pl.DataFrame, 
        period_days: int = 30
    ) -> DataQualityReport:
        """
        Valida qualidade dos dados.
        
        Args:
            df: DataFrame com transações normalizadas
            period_days: Período de análise (dias)
        
        Returns:
            DataQualityReport com análise completa
        
        Example:
            >>> df = pl.DataFrame({
            ...     "transaction_id": ["t1", "t2", "t3"],
            ...     "amount": [-50.0, 100.0, -30.0],
            ...     "transaction_date": [...],
            ...     "description": ["UBER", "SALARIO", "IFOOD"],
            ...     "balance": [1000.0, 1100.0, 1070.0]
            ... })
            >>> 
            >>> validator = DataQualityValidator()
            >>> report = validator.validate(df, period_days=30)
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÃO: DataFrame vazio
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if df.is_empty():
            self.logger.warning("DataFrame vazio. Retornando relatório padrão.")
            return self._get_empty_report()
        
        self.logger.info(
            f"Validando qualidade de {df.height} transações "
            f"(período: {period_days} dias)"
        )
        
        issues = []
        recommendations = []
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANÁLISE 1: COBERTURA TEMPORAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        temporal_coverage, gap_count, temporal_issues = \
            TemporalCoverageAnalysis.analyze(df, period_days)
        
        issues.extend(temporal_issues)
        
        self.logger.debug(
            f"Cobertura temporal: {temporal_coverage:.1%} "
            f"(lacunas: {gap_count})"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANÁLISE 2: ANOMALIAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        anomaly_count, anomaly_issues = AnomalyDetector.detect(df)
        
        issues.extend(anomaly_issues)
        
        self.logger.debug(f"Anomalias detectadas: {anomaly_count}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANÁLISE 3: COMPLETUDE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        completeness_score = self._calculate_completeness(df)
        
        if completeness_score < 0.9:
            issues.append(
                f"Completude baixa: {completeness_score:.1%} dos campos obrigatórios"
            )
        
        self.logger.debug(f"Completude: {completeness_score:.1%}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ANÁLISE 4: CONSISTÊNCIA DE SALDO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        balance_consistency = self._calculate_balance_consistency(df)
        
        if balance_consistency < 0.8:
            issues.append(
                f"Consistência de saldo baixa: {balance_consistency:.1%}"
            )
        
        self.logger.debug(f"Consistência de saldo: {balance_consistency:.1%}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CÁLCULO: CONFIDENCE GLOBAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        overall_confidence = self._calculate_overall_confidence(
            temporal_coverage,
            anomaly_count,
            completeness_score,
            balance_consistency,
            df.height
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # DETERMINAR: QUALITY LEVEL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        quality_level = self._determine_quality_level(overall_confidence)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # GERAR: RECOMENDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        recommendations = self._generate_recommendations(
            temporal_coverage,
            gap_count,
            anomaly_count,
            completeness_score,
            balance_consistency
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOG RESUMO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        self.logger.info(
            f"Validação concluída: "
            f"Confiança={overall_confidence:.1%}, "
            f"Qualidade={quality_level}, "
            f"Problemas={len(issues)}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RETORNAR RELATÓRIO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return DataQualityReport(
            overall_confidence=overall_confidence,
            quality_level=quality_level,
            temporal_coverage=temporal_coverage,
            gap_count=gap_count,
            anomaly_count=anomaly_count,
            completeness_score=completeness_score,
            balance_consistency=balance_consistency,
            issues=issues,
            recommendations=recommendations
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_completeness(self, df: pl.DataFrame) -> float:
        """
        Calcula % de completude dos campos obrigatórios.
        
        Campos obrigatórios:
            - transaction_id
            - amount
            - transaction_date
            - description
        """
        required_fields = ["transaction_id", "amount", "transaction_date", "description"]
        
        # Verificar quais campos existem
        existing_fields = [f for f in required_fields if f in df.columns]
        
        if not existing_fields:
            return 0.0
        
        # Calcular % de valores não-null por campo
        scores = []
        
        for field in existing_fields:
            non_null_count = df.filter(pl.col(field).is_not_null()).height
            field_score = non_null_count / df.height if df.height > 0 else 0.0
            scores.append(field_score)
        
        # Média
        return sum(scores) / len(scores) if scores else 0.0
    
    def _calculate_balance_consistency(self, df: pl.DataFrame) -> float:
        """
        Calcula consistência de saldo.
        
        Verifica se balance[i+1] = balance[i] + amount[i+1]
        
        Retorna % de transações com saldo consistente.
        """
        if "balance" not in df.columns or df.height < 2:
            return 1.0  # Não aplicável, score neutro
        
        # Filtrar rows com balance não-null
        df_with_balance = df.filter(pl.col("balance").is_not_null())
        
        if df_with_balance.height < 2:
            return 1.0
        
        # Ordenar por data
        df_sorted = df_with_balance.sort("transaction_date")
        
        # Calcular saldo esperado
        df_sorted = df_sorted.with_columns([
            pl.col("balance").shift(1).alias("prev_balance"),
            pl.col("amount").alias("current_amount")
        ])
        
        # Remover primeira linha (sem prev_balance)
        df_sorted = df_sorted.slice(1, df_sorted.height - 1)
        
        if df_sorted.is_empty():
            return 1.0
        
        # Verificar consistência
        df_sorted = df_sorted.with_columns([
            (pl.col("prev_balance") + pl.col("current_amount")).alias("expected_balance"),
            pl.col("balance").alias("actual_balance")
        ])
        
        # Tolerância: 0.01 (1 centavo)
        TOLERANCE = 0.01
        
        consistent = df_sorted.filter(
            (pl.col("expected_balance") - pl.col("actual_balance")).abs() <= TOLERANCE
        ).height
        
        total = df_sorted.height
        
        return consistent / total if total > 0 else 1.0
    
    def _calculate_overall_confidence(
        self,
        temporal_coverage: float,
        anomaly_count: int,
        completeness_score: float,
        balance_consistency: float,
        total_records: int
    ) -> float:
        """
        Calcula confiança global (0.0-1.0).
        
        Fórmula ponderada:
            - Cobertura temporal: 30%
            - Completude: 25%
            - Consistência saldo: 25%
            - Ausência de anomalias: 20%
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 1: Cobertura temporal (30%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        coverage_score = temporal_coverage * 0.30
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 2: Completude (25%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        completeness_weighted = completeness_score * 0.25
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 3: Consistência de saldo (25%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        balance_weighted = balance_consistency * 0.25
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 4: Ausência de anomalias (20%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Penaliza proporcionalmente ao número de anomalias
        anomaly_rate = anomaly_count / total_records if total_records > 0 else 0.0
        anomaly_score = max(0.0, 1.0 - anomaly_rate * 10)  # 10 anomalias = score zero
        anomaly_weighted = anomaly_score * 0.20
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SOMA TOTAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        confidence = (
            coverage_score +
            completeness_weighted +
            balance_weighted +
            anomaly_weighted
        )
        
        # Garantir range [0.0, 1.0]
        return max(0.0, min(1.0, confidence))
    
    def _determine_quality_level(self, confidence: float) -> QualityLevel:
        """
        Determina nível de qualidade baseado na confiança.
        
        EXCELLENT: confidence ≥ 0.90
        GOOD: 0.70 ≤ confidence < 0.90
        FAIR: 0.50 ≤ confidence < 0.70
        POOR: confidence < 0.50
        """
        if confidence >= 0.90:
            return "EXCELLENT"
        elif confidence >= 0.70:
            return "GOOD"
        elif confidence >= 0.50:
            return "FAIR"
        else:
            return "POOR"
    
    def _generate_recommendations(
        self,
        temporal_coverage: float,
        gap_count: int,
        anomaly_count: int,
        completeness_score: float,
        balance_consistency: float
    ) -> list[str]:
        """
        Gera recomendações baseadas nos problemas detectados.
        """
        recommendations = []
        
        # Cobertura temporal baixa
        if temporal_coverage < 0.80:
            recommendations.append(
                "⚠️ Cobertura temporal baixa (<80%). "
                "Considere usar Shadow Invoice para preencher lacunas."
            )
        
        # Muitas lacunas
        if gap_count > 5:
            recommendations.append(
                f"⚠️ {gap_count} lacunas detectadas. "
                "Verifique se há problemas de sincronização com Open Finance."
            )
        
        # Anomalias
        if anomaly_count > 0:
            recommendations.append(
                f"⚠️ {anomaly_count} anomalias detectadas. "
                "Revise transações com valores absurdos ou duplicadas."
            )
        
        # Completude baixa
        if completeness_score < 0.90:
            recommendations.append(
                "⚠️ Campos obrigatórios incompletos. "
                "Verifique BankStrategy para o banco problemático."
            )
        
        # Saldo inconsistente
        if balance_consistency < 0.80:
            recommendations.append(
                "⚠️ Saldo inconsistente detectado. "
                "Considere estimar saldo via cumsum (Polars)."
            )
        
        # Se tudo OK
        if not recommendations:
            recommendations.append("✅ Dados de excelente qualidade. Nenhuma ação necessária.")
        
        return recommendations
    
    def _get_empty_report(self) -> DataQualityReport:
        """Retorna relatório padrão para DataFrame vazio."""
        return DataQualityReport(
            overall_confidence=0.0,
            quality_level="POOR",
            temporal_coverage=0.0,
            gap_count=0,
            anomaly_count=0,
            completeness_score=0.0,
            balance_consistency=1.0,  # N/A
            issues=["DataFrame vazio"],
            recommendations=["Nenhum dado disponível para análise"]
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (Convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_data_quality(df: pl.DataFrame, period_days: int = 30) -> DataQualityReport:
    """
    Função helper que encapsula DataQualityValidator.validate().
    
    Útil para imports diretos:
        from app.etl.data_quality import validate_data_quality
    
    Args:
        df: DataFrame com transações
        period_days: Período de análise
    
    Returns:
        DataQualityReport
    
    Example:
        >>> report = validate_data_quality(df, period_days=30)
        >>> print(report.overall_confidence)
        0.85
    """
    validator = DataQualityValidator()
    return validator.validate(df, period_days)
