"""
TrendDetector — detecta direção de tendência por categoria e por fonte de pagamento.

Compara o período recente (últimos 90 dias, janela do profiler) contra o baseline
histórico (90–540 dias anteriores, janela do PersonalBaseline) para classificar
cada sinal como SUBINDO, ESTAVEL, CAINDO, REEMERGINDO ou DESAPARECENDO.

Sinais cobertos:
  - Por categoria de gasto: alimentacao, farmacia, etc. (via PersonalBaseline)
  - _delivery:  pedidos em apps de delivery (is_delivery L2, separado de alimentacao)
  - _income:    renda mensal
  - _credit:    gasto via cartão de crédito
  - _debit:     gasto via débito / conta corrente
  - _pix:       transferências e pagamentos via PIX (payment_method="PIX")

delivery e _pix exigem df enriquecido pelo TransactionFeatureEnricher.
Quando enriched_recent_df=None, esses sinais são omitidos da saída.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import polars as pl

from app.optimizer.detectors.personal_baseline import PersonalBaseline

_MIN_MONTHLY = 15.0     # R$/mês mínimo para considerar sinal ativo
_THRESHOLD_UP = 1.20    # +20% → SUBINDO
_THRESHOLD_DOWN = 0.80  # -20% → CAINDO

_WINDOW_DAYS = 540      # janela histórica (espelho de compute_personal_baseline)
_RECENT_DAYS = 90       # janela recente excluída do baseline


@dataclass(frozen=True)
class CategoryTrend:
    direction: str          # SUBINDO | ESTAVEL | CAINDO | REEMERGINDO | DESAPARECENDO
    ratio: float            # current / baseline; float("inf") quando baseline=0 e current>0
    baseline_monthly: float
    current_monthly: float

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "ratio": self.ratio,
            "baseline_monthly": self.baseline_monthly,
            "current_monthly": self.current_monthly,
        }


def _classify(current: float, baseline: float) -> tuple[str, float]:
    """Retorna (direction, ratio) dado current e baseline em R$/mês."""
    current_active = current >= _MIN_MONTHLY
    baseline_active = baseline >= _MIN_MONTHLY

    if not baseline_active and not current_active:
        return "ESTAVEL", 1.0
    if not baseline_active and current_active:
        return "REEMERGINDO", float("inf")
    if baseline_active and not current_active:
        return "DESAPARECENDO", 0.0

    ratio = current / baseline
    if ratio >= _THRESHOLD_UP:
        return "SUBINDO", round(ratio, 3)
    if ratio <= _THRESHOLD_DOWN:
        return "CAINDO", round(ratio, 3)
    return "ESTAVEL", round(ratio, 3)


def _months_in(df: pl.DataFrame) -> int:
    """Conta meses distintos no DataFrame."""
    if df.is_empty() or "date" not in df.columns:
        return 0
    return (
        df.with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        )
        .select("ym")
        .unique()
        .height
    )


def _monthly_expenses_filtered(df: pl.DataFrame, mask: pl.Expr) -> float:
    """
    Gasto médio mensal (R$/mês) para transações que satisfazem `mask`.

    mask deve ser uma expressão Polars que seleciona um subconjunto das despesas
    (amount < 0). O denominador é o número de meses distintos no df inteiro,
    não apenas no subconjunto filtrado, para normalizar corretamente.
    """
    if df.is_empty():
        return 0.0
    months = _months_in(df)
    if months == 0:
        return 0.0
    expenses = df.filter((pl.col("amount") < 0) & mask)
    if expenses.is_empty():
        return 0.0
    return round(float(expenses["amount"].sum()) * -1 / months, 2)


class TrendDetector:

    def detect(
        self,
        df: pl.DataFrame,
        current_spend_by_category: dict[str, float],
        current_spend_by_source: dict[str, float],
        current_monthly_income: float,
        personal_baseline: PersonalBaseline,
        reference_date: Optional[date] = None,
        enriched_recent_df: Optional[pl.DataFrame] = None,
    ) -> dict[str, dict]:
        """
        Detecta tendência por categoria, fonte de pagamento e renda.

        Args:
            df: DataFrame COMPLETO de transações (não filtrado a 90 dias) —
                necessário para calcular o baseline histórico de renda e fonte.
            current_spend_by_category: gasto médio mensal recente por categoria
                (saída de ConsumptionProfiler._spend_by_category).
            current_spend_by_source: gasto médio mensal recente por fonte
                (saída de ConsumptionProfiler._spend_by_source).
            current_monthly_income: renda média mensal recente (R$/mês).
            personal_baseline: baseline histórico por categoria (90–540 dias atrás).
            reference_date: data de referência (default=hoje).
            enriched_recent_df: df dos últimos 90 dias já enriquecido pelo
                TransactionFeatureEnricher. Quando fornecido, habilita os sinais
                _delivery e _pix. Quando None, esses sinais são omitidos.

        Returns:
            Dict sinal → {direction, ratio, baseline_monthly, current_monthly}.
        """
        if df is None or df.is_empty():
            return {}

        ref = reference_date or date.today()

        if df["date"].dtype != pl.Date:
            df = df.with_columns(pl.col("date").cast(pl.Date))

        trends: dict[str, dict] = {}

        # ── 1. Tendências por categoria de gasto ─────────────────────────────
        # Só quando o baseline tem dados confiáveis (≥ 2 meses de histórico).
        if personal_baseline.has_data():
            all_categories = (
                set(current_spend_by_category.keys())
                | set(personal_baseline.category_monthly_avg.keys())
            )
            for cat in all_categories:
                if cat in ("outros",):
                    continue
                current = current_spend_by_category.get(cat, 0.0)
                baseline = personal_baseline.monthly_avg(cat)
                direction, ratio = _classify(current, baseline)
                trends[cat] = CategoryTrend(
                    direction=direction,
                    ratio=ratio,
                    baseline_monthly=round(baseline, 2),
                    current_monthly=round(current, 2),
                ).to_dict()

        # ── 2. Tendência de renda ─────────────────────────────────────────────
        historical_income = self._historical_income(df, ref)
        if historical_income > 0 or current_monthly_income > 0:
            inc_direction, inc_ratio = _classify(current_monthly_income, historical_income)
            trends["_income"] = CategoryTrend(
                direction=inc_direction,
                ratio=inc_ratio,
                baseline_monthly=round(historical_income, 2),
                current_monthly=round(current_monthly_income, 2),
            ).to_dict()

        # ── 3. Tendência por fonte de pagamento (crédito / débito) ───────────
        hist_source = self._historical_source(df, ref)
        for source in ("credit", "debit"):
            current_s = current_spend_by_source.get(source, 0.0)
            baseline_s = hist_source.get(source, 0.0)
            if current_s > 0 or baseline_s > 0:
                direction_s, ratio_s = _classify(current_s, baseline_s)
                trends[f"_{source}"] = CategoryTrend(
                    direction=direction_s,
                    ratio=ratio_s,
                    baseline_monthly=round(baseline_s, 2),
                    current_monthly=round(current_s, 2),
                ).to_dict()

        # ── 4. PIX e Delivery (requerem df enriquecido) ───────────────────────
        if enriched_recent_df is not None and not enriched_recent_df.is_empty():
            enriched_hist = self._build_enriched_historical(df, ref)
            self._add_pix_trend(trends, enriched_recent_df, enriched_hist)
            self._add_delivery_trend(trends, enriched_recent_df, enriched_hist)

        return trends

    # ── Sinais enriquecidos ───────────────────────────────────────────────────

    def _build_enriched_historical(self, df: pl.DataFrame, ref: date) -> pl.DataFrame:
        """Filtra a janela histórica e enriquece com payment_method e is_delivery."""
        from app.optimizer.feature_store import TransactionFeatureEnricher
        cutoff_start = ref - timedelta(days=_WINDOW_DAYS)
        cutoff_end = ref - timedelta(days=_RECENT_DAYS)
        hist = df.filter(
            (pl.col("date") >= cutoff_start) & (pl.col("date") < cutoff_end)
        )
        if "context_type" in hist.columns:
            hist = hist.filter(
                pl.col("context_type").is_null() | (pl.col("context_type") != "PJ")
            )
        if hist.is_empty():
            return hist
        return TransactionFeatureEnricher().enrich(hist)

    def _add_pix_trend(
        self,
        trends: dict,
        recent: pl.DataFrame,
        hist: pl.DataFrame,
    ) -> None:
        if "payment_method" not in recent.columns:
            return
        pix_mask = pl.col("payment_method") == "PIX"
        pix_curr = _monthly_expenses_filtered(recent, pix_mask)
        pix_hist = _monthly_expenses_filtered(hist, pix_mask) if not hist.is_empty() and "payment_method" in hist.columns else 0.0
        if pix_curr > 0 or pix_hist > 0:
            direction, ratio = _classify(pix_curr, pix_hist)
            trends["_pix"] = CategoryTrend(
                direction=direction,
                ratio=ratio,
                baseline_monthly=round(pix_hist, 2),
                current_monthly=round(pix_curr, 2),
            ).to_dict()

    def _add_delivery_trend(
        self,
        trends: dict,
        recent: pl.DataFrame,
        hist: pl.DataFrame,
    ) -> None:
        if "is_delivery" not in recent.columns:
            return
        delivery_mask = pl.col("is_delivery") == True
        del_curr = _monthly_expenses_filtered(recent, delivery_mask)
        del_hist = _monthly_expenses_filtered(hist, delivery_mask) if not hist.is_empty() and "is_delivery" in hist.columns else 0.0
        if del_curr > 0 or del_hist > 0:
            direction, ratio = _classify(del_curr, del_hist)
            trends["_delivery"] = CategoryTrend(
                direction=direction,
                ratio=ratio,
                baseline_monthly=round(del_hist, 2),
                current_monthly=round(del_curr, 2),
            ).to_dict()

    # ── Helpers históricos (operam no df bruto completo) ─────────────────────

    def _historical_income(self, df: pl.DataFrame, ref: date) -> float:
        """Renda média mensal na janela histórica [ref-540d, ref-90d)."""
        cutoff_start = ref - timedelta(days=_WINDOW_DAYS)
        cutoff_end = ref - timedelta(days=_RECENT_DAYS)
        hist = df.filter(
            (pl.col("date") >= cutoff_start)
            & (pl.col("date") < cutoff_end)
            & (pl.col("amount") > 0)
        )
        if "context_type" in hist.columns:
            hist = hist.filter(
                pl.col("context_type").is_null() | (pl.col("context_type") != "PJ")
            )
        months = _months_in(hist)
        if months == 0 or hist.is_empty():
            return 0.0
        return round(float(hist["amount"].sum()) / months, 2)

    def _historical_source(self, df: pl.DataFrame, ref: date) -> dict[str, float]:
        """Gasto médio mensal por fonte (credit/debit) na janela histórica."""
        cutoff_start = ref - timedelta(days=_WINDOW_DAYS)
        cutoff_end = ref - timedelta(days=_RECENT_DAYS)
        hist = df.filter(
            (pl.col("date") >= cutoff_start)
            & (pl.col("date") < cutoff_end)
            & (pl.col("amount") < 0)
        )
        if "context_type" in hist.columns:
            hist = hist.filter(
                pl.col("context_type").is_null() | (pl.col("context_type") != "PJ")
            )
        if hist.is_empty() or "transaction_type" not in hist.columns:
            return {}
        months = _months_in(hist)
        if months == 0:
            return {}
        result = (
            hist
            .with_columns(
                pl.when(pl.col("transaction_type").is_null())
                .then(pl.lit("unknown"))
                .when(pl.col("transaction_type").cast(pl.Utf8, strict=False).str.to_uppercase() == "DEBIT")
                .then(pl.lit("debit"))
                .otherwise(pl.lit("credit"))
                .alias("source")
            )
            .filter(pl.col("source") != "unknown")
            .group_by("source")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .with_columns((pl.col("total") / months).alias("monthly_avg"))
        )
        return {
            row["source"]: round(row["monthly_avg"], 2)
            for row in result.to_dicts()
        }
