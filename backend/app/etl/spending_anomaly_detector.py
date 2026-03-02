"""
app/etl/spending_anomaly_detector.py - Detecção de Anomalias de Gasto (M1.1)

RESPONSABILIDADE:
    Detecta gastos fora do padrão histórico do usuário, por transação.

    Diferente do DataQualityValidator (que verifica integridade estrutural dos dados),
    este módulo analisa comportamento: "isso é incomum PARA ESTE USUÁRIO".

TIPOS DE ANOMALIA:
    UNUSUAL_AMOUNT   — valor > (média + 2σ) na categoria (baseline histórico)
    NEW_MERCHANT     — estabelecimento nunca visto no histórico + valor ≥ R$ 200
    FREQUENCY_SPIKE  — frequência diária ≥ 3× a média histórica na categoria
    DUPLICATE_SUSPECT — mesmo merchant e valor idêntico dentro de 48h

INTEGRAÇÃO:
    - Chamado após classificação no ETL runner (app/etl/runner.py)
    - Anomalias expostas via GET /api/v1/alerts/{user_id}
    - Agente usa `description` nos alertas proativos:
        "Notei um gasto incomum de R$ 890 em Alimentação — 3x acima do seu padrão."

LIMITAÇÕES CONHECIDAS:
    - DUPLICATE_SUSPECT compara datas (não timestamps) por restrição do schema.
      Janela de 48h é aproximada como 2 dias calendário.
    - NEW_MERCHANT usa a descrição normalizada como proxy de merchant.
      Estabelecimentos com nomes variáveis (ex: "IFOOD*RESTAURANTE_X") podem
      gerar falsos positivos. A M1.1v2 pode adicionar normalização por prefixo.
    - UNUSUAL_AMOUNT exige ≥ 5 transações históricas por categoria para evitar
      baselines instáveis. Categorias raras nunca disparam este alerta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

import polars as pl

if TYPE_CHECKING:
    from app.etl.income_profiler import IncomeProfile

logger = logging.getLogger(__name__)

# Limiar de confiança para usar income_profile nos thresholds
_INCOME_CONFIDENCE_THRESHOLD: float = 0.5

# UNUSUAL_AMOUNT: % da renda mensal que torna um gasto "incomum" em termos absolutos
# Ex: 15% de R$8.000/mês = R$1.200 — mesmo que dentro do padrão histórico, é significativo
_INCOME_PCT_UNUSUAL: float = 0.15

# NEW_MERCHANT: % da renda mensal como threshold mínimo para alertar merchant novo
# Ex: 2% de R$8.000/mês = R$160 (vs fixo R$200)
_INCOME_PCT_NEW_MERCHANT: float = 0.02


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# UNUSUAL_AMOUNT: desvios padrão acima da média histórica para disparar alerta
_UNUSUAL_SIGMA: float = 2.0

# NEW_MERCHANT: valor mínimo para alertar transação em merchant novo
# (filtra ruído de pequenas compras no cartão de débito/passagem)
_NEW_MERCHANT_MIN_VALUE: float = 200.0

# FREQUENCY_SPIKE: multiplicador sobre a média diária histórica por categoria
_FREQUENCY_SPIKE_FACTOR: float = 3.0

# DUPLICATE_SUSPECT: janela temporal expressa em dias calendário
# (48h reais → 2 dias, dado que o schema tem only date, não timestamp)
_DUPLICATE_WINDOW_DAYS: int = 2

# Mínimo de transações históricas por categoria para baseline confiável
# Abaixo deste valor, UNUSUAL_AMOUNT não é calculado para evitar falsos positivos
_MIN_HISTORY_COUNT: int = 5

# Categorias que representam entradas/movimentos não-consumo — excluídas do UNUSUAL_AMOUNT
_SKIP_CATEGORIES: frozenset[str] = frozenset({"Transferência", "Investimento", "Outros"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIPOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AnomalyType(str, Enum):
    UNUSUAL_AMOUNT    = "UNUSUAL_AMOUNT"
    NEW_MERCHANT      = "NEW_MERCHANT"
    FREQUENCY_SPIKE   = "FREQUENCY_SPIKE"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"


Severity = Literal["INFO", "WARNING", "ALERT"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Anomaly:
    """
    Representa uma transação anômala detectada.

    Attributes:
        transaction_id: ID da transação (ou descrição truncada se ausente)
        anomaly_type: Tipo de anomalia detectada
        severity: INFO < WARNING < ALERT
        description: Texto legível pelo usuário / LLM
        baseline_value: Valor de referência histórico (média, contagem, etc.)
        actual_value: Valor observado na transação anômala
        deviation_factor: Quanto desviou do baseline (ex: 3.2 = 3.2× acima)

    Example:
        >>> anomaly.description
        'Gasto de R$ 890,00 em Alimentação — 3.2x acima da sua média (R$ 278,00)'
        >>> anomaly.severity
        'WARNING'
    """
    transaction_id: str
    anomaly_type: AnomalyType
    severity: Severity
    description: str
    baseline_value: float
    actual_value: float
    deviation_factor: float

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "description": self.description,
            "baseline_value": self.baseline_value,
            "actual_value": self.actual_value,
            "deviation_factor": self.deviation_factor,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SpendingAnomalyDetector:
    """
    Detecta anomalias de gasto comparando transações recentes ao histórico.

    Todos os 4 detectores operam sobre despesas (amount < 0 no schema original),
    convertidas para positivo internamente.

    Args:
        lookback_months: Meses de histórico usados para construir o baseline.
            Não filtra o history_df — responsabilidade do chamador passar o
            DataFrame já recortado na janela desejada.

    Example:
        >>> detector = SpendingAnomalyDetector()
        >>> anomalies = detector.detect(
        ...     transactions_df=recent_df,   # último mês
        ...     history_df=history_df,       # últimos 3 meses
        ... )
        >>> for a in anomalies:
        ...     print(f"[{a.severity}] {a.description}")
        [WARNING] Gasto de R$ 890,00 em Alimentação — 3.2x acima da sua média
        [INFO] Novo estabelecimento: 'AMAZON PRIME' (R$ 239,90)
        [ALERT] Possível cobrança duplicada: 'NETFLIX' R$ 55,90 — transação similar há 24h
    """

    def __init__(self, lookback_months: int = 3):
        self._lookback_months = lookback_months

    def detect(
        self,
        transactions_df: pl.DataFrame,
        history_df: pl.DataFrame,
        income_profile: Optional["IncomeProfile"] = None,
    ) -> list[Anomaly]:
        """
        Executa todos os detectores e agrega as anomalias encontradas.

        Args:
            transactions_df: Transações recentes a analisar (tipicamente último mês).
            history_df: Histórico de referência para construir baseline.
                Deve incluir o mesmo período de transactions_df para que
                DUPLICATE_SUSPECT não produza duplicatas do próprio histórico.
            income_profile: IncomeProfile do IncomeProfiler (opcional).
                Quando fornecido e confidence ≥ 0.5, calibra thresholds pelo
                nível de renda real do usuário:
                - UNUSUAL_AMOUNT: enriquece descrição com % da renda mensal.
                - NEW_MERCHANT: threshold mínimo = max(100, 2% da renda).

        Returns:
            Lista de Anomaly ordenada por severity (ALERT → WARNING → INFO).
        """
        if transactions_df.is_empty() or history_df.is_empty():
            return []

        recent  = self._filter_expenses(transactions_df)
        history = self._filter_expenses(history_df)

        if recent.is_empty():
            return []

        # Renda mensal confiável para calibrar thresholds (None = usar defaults fixos)
        income_monthly: float | None = None
        if (
            income_profile is not None
            and income_profile.confidence >= _INCOME_CONFIDENCE_THRESHOLD
            and income_profile.monthly_net_income > 0
        ):
            income_monthly = income_profile.monthly_net_income

        anomalies: list[Anomaly] = []
        anomalies.extend(self._detect_unusual_amount(recent, history, income_monthly))
        anomalies.extend(self._detect_new_merchant(recent, history, income_monthly))
        anomalies.extend(self._detect_frequency_spike(recent, history))
        anomalies.extend(self._detect_duplicate_suspect(recent))

        # Ordenar por severidade
        _order = {"ALERT": 0, "WARNING": 1, "INFO": 2}
        anomalies.sort(key=lambda a: _order.get(a.severity, 3))

        logger.info(
            f"SpendingAnomalyDetector: {len(recent)} transações analisadas, "
            f"{len(anomalies)} anomalias "
            f"({sum(1 for a in anomalies if a.severity == 'ALERT')} ALERT, "
            f"{sum(1 for a in anomalies if a.severity == 'WARNING')} WARNING, "
            f"{sum(1 for a in anomalies if a.severity == 'INFO')} INFO)"
        )

        return anomalies

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _filter_expenses(df: pl.DataFrame) -> pl.DataFrame:
        """Filtra despesas e inverte o sinal (positivo = magnitude do gasto)."""
        expenses = df.filter(pl.col("amount") < 0)
        return expenses.with_columns(pl.col("amount").abs().alias("amount"))

    @staticmethod
    def _tx_id(row: dict) -> str:
        """Extrai o identificador da transação com fallback para descrição."""
        return row.get("transaction_id") or str(row.get("description", "?"))[:30]

    # ──────────────────────────────────────────────────────────────────────
    # UNUSUAL_AMOUNT
    # ──────────────────────────────────────────────────────────────────────

    def _detect_unusual_amount(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        income_monthly: float | None = None,
    ) -> list[Anomaly]:
        """
        Sinaliza transações com valor > avg + 2σ na categoria.

        Baseline é calculado somente em categorias com ≥ _MIN_HISTORY_COUNT
        transações históricas para evitar baselines instáveis (ex: "Viagem"
        com 1 transação por ano produziria σ=0 e alertaria em qualquer gasto).

        Quando income_monthly disponível, a descrição inclui "X% da renda mensal"
        e transações > _INCOME_PCT_UNUSUAL × renda são sinalizadas mesmo que
        dentro do padrão histórico (gasto absoluto alto para o nível de renda).
        """
        if "category" not in recent.columns or "category" not in history.columns:
            return []

        cat_stats = (
            history
            .filter(~pl.col("category").is_in(list(_SKIP_CATEGORIES)))
            .group_by("category")
            .agg([
                pl.col("amount").mean().alias("avg"),
                pl.col("amount").std(ddof=1).fill_null(0.0).alias("std"),
                pl.col("amount").count().alias("n"),
            ])
            .filter(pl.col("n") >= _MIN_HISTORY_COUNT)
        )

        if cat_stats.is_empty():
            return []

        flagged = (
            recent
            .filter(~pl.col("category").is_in(list(_SKIP_CATEGORIES)))
            .join(cat_stats, on="category", how="inner")
            .with_columns(
                (pl.col("avg") + _UNUSUAL_SIGMA * pl.col("std")).alias("threshold")
            )
            .filter(pl.col("amount") > pl.col("threshold"))
        )

        # Threshold absoluto por renda: gasto > 15% da renda mensal é relevante
        # mesmo que não seja estatisticamente anômalo no histórico da categoria.
        income_threshold = (
            income_monthly * _INCOME_PCT_UNUSUAL if income_monthly else None
        )

        anomalies: list[Anomaly] = []
        for row in flagged.iter_rows(named=True):
            avg    = row["avg"]
            amount = row["amount"]
            factor = round(amount / avg, 2) if avg > 0 else 0.0
            cat    = row["category"]

            # Contexto de renda: só inclui se amount for significativo vs renda
            income_context = ""
            if income_monthly and income_threshold and amount >= income_threshold:
                income_pct = amount / income_monthly * 100
                income_context = f" ({income_pct:.0f}% da renda mensal)"

            anomalies.append(Anomaly(
                transaction_id=self._tx_id(row),
                anomaly_type=AnomalyType.UNUSUAL_AMOUNT,
                severity="WARNING",
                description=(
                    f"Gasto de R$ {amount:,.2f} em {cat} — "
                    f"{factor:.1f}x acima da sua média (R$ {avg:,.2f})"
                    f"{income_context}"
                ),
                baseline_value=round(avg, 2),
                actual_value=round(amount, 2),
                deviation_factor=factor,
            ))
        return anomalies

    # ──────────────────────────────────────────────────────────────────────
    # NEW_MERCHANT
    # ──────────────────────────────────────────────────────────────────────

    def _detect_new_merchant(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        income_monthly: float | None = None,
    ) -> list[Anomaly]:
        """
        Sinaliza transações de valor alto em estabelecimentos nunca vistos.

        Proxy de merchant = description normalizada (lowercase + strip).
        Transações abaixo do threshold são ignoradas para reduzir ruído de
        pequenas compras avulsas (ex: estacionamento R$ 10).

        Threshold dinâmico quando income_monthly disponível:
            max(100.0, income_monthly × _INCOME_PCT_NEW_MERCHANT)
        Isso calibra o limite ao nível de renda — para quem ganha R$3.000/mês,
        R$60 já pode ser relevante; para R$15.000/mês, R$300 faz mais sentido.
        Caso contrário, usa _NEW_MERCHANT_MIN_VALUE (R$200 fixo).
        """
        if "description" not in recent.columns or "description" not in history.columns:
            return []

        # Threshold calibrado pela renda quando disponível
        min_value = (
            max(100.0, income_monthly * _INCOME_PCT_NEW_MERCHANT)
            if income_monthly
            else _NEW_MERCHANT_MIN_VALUE
        )

        # Série de merchants conhecidos mantida como pl.Series para is_in() direto
        # (evita roundtrip para Python set e de volta para list)
        known_series: pl.Series = (
            history
            .select(pl.col("description").str.to_lowercase().str.strip_chars())
            .drop_nulls()
            .get_column("description")
        )

        # Filtrar recentes de alto valor com merchant novo (vectorizado)
        flagged = (
            recent
            .filter(pl.col("amount") >= min_value)
            .with_columns(
                pl.col("description").str.to_lowercase().str.strip_chars().alias("_desc_norm")
            )
            .filter(~pl.col("_desc_norm").is_in(known_series))
        )

        anomalies: list[Anomaly] = []
        for row in flagged.iter_rows(named=True):
            amount = row["amount"]
            raw_desc = row.get("description") or row["_desc_norm"]
            anomalies.append(Anomaly(
                transaction_id=self._tx_id(row),
                anomaly_type=AnomalyType.NEW_MERCHANT,
                severity="INFO",
                description=(
                    f"Novo estabelecimento: '{raw_desc}' (R$ {amount:,.2f}) "
                    f"— nunca visto no seu histórico"
                ),
                baseline_value=0.0,
                actual_value=round(amount, 2),
                deviation_factor=0.0,
            ))
        return anomalies

    # ──────────────────────────────────────────────────────────────────────
    # FREQUENCY_SPIKE
    # ──────────────────────────────────────────────────────────────────────

    def _detect_frequency_spike(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
    ) -> list[Anomaly]:
        """
        Sinaliza dias com frequência de transações ≥ 3× a média histórica.

        O transaction_id é sintético (freq_{categoria}_{data}) porque o alerta
        é por (category, date), não por transação individual.
        """
        required = {"category", "date"}
        if not required.issubset(recent.columns) or not required.issubset(history.columns):
            return []

        # Média diária de transações por categoria no histórico
        hist_avg = (
            history
            .with_columns(pl.col("date").cast(pl.Date))
            .group_by(["category", "date"])
            .agg(pl.len().alias("daily_count"))
            .group_by("category")
            .agg(pl.col("daily_count").mean().alias("avg_daily"))
        )

        if hist_avg.is_empty():
            return []

        # Contagem por (date, category) nas transações recentes, comparada ao avg
        recent_daily = (
            recent
            .with_columns(pl.col("date").cast(pl.Date))
            .group_by(["date", "category"])
            .agg(pl.len().alias("daily_count"))
            # inner intencional: categorias sem histórico não têm baseline →
            # não é possível determinar se há spike → descartadas silenciosamente.
            .join(hist_avg, on="category", how="inner")
            .with_columns(
                (pl.col("daily_count") / pl.col("avg_daily")).alias("spike_factor")
            )
            .filter(pl.col("spike_factor") >= _FREQUENCY_SPIKE_FACTOR)
        )

        anomalies: list[Anomaly] = []
        for row in recent_daily.iter_rows(named=True):
            cat    = row["category"]
            daily  = int(row["daily_count"])
            avg    = row["avg_daily"]
            factor = round(row["spike_factor"], 1)
            date_s = str(row["date"])
            anomalies.append(Anomaly(
                transaction_id=f"freq_{cat}_{date_s}",
                anomaly_type=AnomalyType.FREQUENCY_SPIKE,
                severity="WARNING",
                description=(
                    f"{daily} transações em {cat} no dia {date_s} — "
                    f"{factor:.1f}x acima da frequência habitual ({avg:.1f}/dia)"
                ),
                baseline_value=round(avg, 2),
                actual_value=float(daily),
                deviation_factor=factor,
            ))
        return anomalies

    # ──────────────────────────────────────────────────────────────────────
    # DUPLICATE_SUSPECT
    # ──────────────────────────────────────────────────────────────────────

    def _detect_duplicate_suspect(self, recent: pl.DataFrame) -> list[Anomaly]:
        """
        Sinaliza pares de transações com mesmo merchant e mesmo valor dentro
        de _DUPLICATE_WINDOW_DAYS dias.

        Opera exclusivamente em `recent` (o histórico não é relevante aqui:
        uma cobrança duplicada é sempre intra-período imediato).

        Cada transação é reportada no máximo uma vez (break no primeiro match)
        para evitar alertas em cascata em cobranças recorrentes legítimas
        (ex: plano parcelado com mesmo valor mensal).

        Limitação: usa datas (não timestamps) — janela é 2 dias calendário,
        não exatamente 48h. Aceito como simplificação do schema atual.
        """
        if "description" not in recent.columns or "date" not in recent.columns:
            return []

        rows = (
            recent
            .with_columns([
                pl.col("date").cast(pl.Date),
                pl.col("description").str.to_lowercase().str.strip_chars().alias("_desc_norm"),
            ])
            .drop_nulls(subset=["date"])   # null date → TypeError em subtração de datas
            .sort("date")
            .to_dicts()
        )

        seen: list[dict] = []
        anomalies: list[Anomaly] = []

        for row in rows:
            desc_norm = row["_desc_norm"]
            amount    = row["amount"]
            tx_date   = row["date"]  # datetime.date após to_dicts()

            for prev in reversed(seen):  # mais recentes primeiro → break mais rápido
                days_apart = (tx_date - prev["date"]).days
                if days_apart > _DUPLICATE_WINDOW_DAYS:
                    break  # lista ordenada por data — os demais são ainda mais antigos
                if prev["_desc_norm"] == desc_norm and abs(prev["amount"] - amount) < 0.01:
                    raw_desc = row.get("description") or desc_norm
                    anomalies.append(Anomaly(
                        transaction_id=self._tx_id(row),
                        anomaly_type=AnomalyType.DUPLICATE_SUSPECT,
                        severity="ALERT",
                        description=(
                            f"Possível cobrança duplicada: '{raw_desc}' "
                            f"R$ {amount:,.2f} — transação similar há {days_apart} "
                            f"{'dia' if days_apart == 1 else 'dias'}"
                        ),
                        baseline_value=round(prev["amount"], 2),
                        actual_value=round(amount, 2),
                        deviation_factor=1.0,
                    ))
                    break  # reportar uma vez por transação

            seen.append(row)

        return anomalies


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_spending_anomalies(
    transactions_df: pl.DataFrame,
    history_df: pl.DataFrame,
    lookback_months: int = 3,
    income_profile: Optional["IncomeProfile"] = None,
) -> list[Anomaly]:
    """
    Wrapper de conveniência para SpendingAnomalyDetector.detect().

    Example:
        >>> anomalies = detect_spending_anomalies(recent_df, history_df, income_profile=ip)
        >>> alerts = [a for a in anomalies if a.severity == "ALERT"]
    """
    return SpendingAnomalyDetector(lookback_months=lookback_months).detect(
        transactions_df=transactions_df,
        history_df=history_df,
        income_profile=income_profile,
    )


__all__ = [
    "SpendingAnomalyDetector",
    "Anomaly",
    "AnomalyType",
    "detect_spending_anomalies",
]
