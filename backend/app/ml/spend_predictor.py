# app/ml/spend_predictor.py
# SpendPredictor — T3.2: Predição de gastos futuros por categoria

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import polars as pl

logger = logging.getLogger(__name__)

_MIN_MONTHS_FOR_PROPHET = 6
_FALLBACK_CI_FACTOR = 0.20  # ±20% para intervalo de confiança do moving average

PredictionMethod = Literal["prophet", "moving_average"]


@dataclass(frozen=True)
class SpendPrediction:
    """Resultado de previsão de gastos para os próximos 30 dias."""

    category: str              # categoria prevista, ou "total"
    predicted_spend: float     # valor central previsto (R$)
    lower_bound: float         # P10 (Prophet) ou -20% (moving average)
    upper_bound: float         # P90 (Prophet) ou +20% (moving average)
    method: PredictionMethod
    months_of_data: int        # meses de histórico usados no cálculo
    reference_date: date       # data base usada como "hoje"

    @property
    def confidence_interval(self) -> tuple[float, float]:
        return (self.lower_bound, self.upper_bound)


class SpendPredictor:
    """
    Prediz gastos futuros por categoria usando Prophet ou média móvel.

    Requisito para Prophet: usuário com ≥ 6 meses de histórico.
    Fallback (< 6 meses ou Prophet não instalado): média dos últimos 3 meses.

    Interface de uso:
        predictor = SpendPredictor()

        # Previsão total
        total = predictor.predict_next_30d(transactions_df)

        # Previsão por categoria específica
        food = predictor.predict_next_30d(transactions_df, category="Alimentação")

        # Previsão de todas as categorias de uma vez
        by_cat = predictor.predict_by_category(transactions_df)
    """

    def predict_next_30d(
        self,
        transactions_df: pl.DataFrame,
        category: str | None = None,
        reference_date: date | None = None,
    ) -> SpendPrediction:
        """
        Retorna previsão de gasto para os próximos 30 dias.

        Args:
            transactions_df: DataFrame com colunas `date` (pl.Date), `amount` (pl.Float64),
                             e opcionalmente `category` (pl.Utf8).
            category: Categoria a filtrar. None = total (todas as despesas).
            reference_date: Data base. Default: hoje.

        Returns:
            SpendPrediction com predicted_spend, confidence_interval e método usado.
        """
        ref = reference_date or date.today()
        cat_label = category or "total"

        if transactions_df is None or transactions_df.is_empty():
            return self._empty_prediction(cat_label, ref)

        expenses = self._filter_expenses(transactions_df, category)

        if expenses.is_empty():
            return self._empty_prediction(cat_label, ref)

        months = self._count_months(expenses)

        if months >= _MIN_MONTHS_FOR_PROPHET:
            try:
                return self._prophet_predict(expenses, cat_label, months, ref)
            except ImportError:
                logger.info(
                    "Prophet não instalado — usando média móvel para '%s'", cat_label
                )
            except Exception as exc:
                logger.warning(
                    "Prophet falhou para '%s': %s — usando média móvel", cat_label, exc
                )

        return self._moving_average_predict(expenses, cat_label, months, ref)

    def predict_by_category(
        self,
        transactions_df: pl.DataFrame,
        min_monthly_spend: float = 50.0,
        reference_date: date | None = None,
    ) -> dict[str, SpendPrediction]:
        """
        Prediz gastos para cada categoria presente no DataFrame.

        Args:
            transactions_df: DataFrame com `date`, `amount`, `category`.
            min_monthly_spend: Ignora categorias com gasto médio < esse valor (R$/mês).
            reference_date: Data base. Default: hoje.

        Returns:
            Dict mapeando nome da categoria → SpendPrediction.
            Inclui sempre a chave "total".
        """
        ref = reference_date or date.today()
        results: dict[str, SpendPrediction] = {}

        results["total"] = self.predict_next_30d(transactions_df, None, ref)

        if "category" not in transactions_df.columns:
            return results

        expenses = transactions_df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return results

        months = max(self._count_months(expenses), 1)
        categories = (
            expenses
            .group_by("category")
            .agg(pl.col("amount").sum().abs().alias("total_spend"))
            .filter(pl.col("total_spend") / months >= min_monthly_spend)
            .sort("total_spend", descending=True)
            .get_column("category")
            .to_list()
        )

        for cat in categories:
            results[cat] = self.predict_next_30d(transactions_df, cat, ref)

        return results

    # ─── Implementações de predição ──────────────────────────────────────────────

    def _prophet_predict(
        self,
        expenses: pl.DataFrame,
        category: str,
        months: int,
        ref: date,
    ) -> SpendPrediction:
        import pandas as pd
        from prophet import Prophet  # lazy — não quebra se não instalado

        daily = (
            expenses
            .with_columns(pl.col("date").alias("ds"))
            .group_by("ds")
            .agg(pl.col("amount").sum().abs().alias("y"))
            .sort("ds")
        )

        pdf = daily.to_pandas()
        pdf["ds"] = pd.to_datetime(pdf["ds"])

        model = Prophet(
            yearly_seasonality=months >= 12,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80,  # P10–P90
        )
        model.fit(pdf)

        future = model.make_future_dataframe(periods=30)
        forecast = model.predict(future)

        next_30 = forecast.tail(30)
        predicted = float(next_30["yhat"].clip(lower=0).sum())
        lower = float(next_30["yhat_lower"].clip(lower=0).sum())
        upper = float(next_30["yhat_upper"].clip(lower=0).sum())

        return SpendPrediction(
            category=category,
            predicted_spend=round(predicted, 2),
            lower_bound=round(lower, 2),
            upper_bound=round(upper, 2),
            method="prophet",
            months_of_data=months,
            reference_date=ref,
        )

    def _moving_average_predict(
        self,
        expenses: pl.DataFrame,
        category: str,
        months: int,
        ref: date,
    ) -> SpendPrediction:
        """Média dos últimos 3 meses disponíveis como previsão base."""
        window_months = min(3, max(months, 1))
        cutoff = ref - timedelta(days=window_months * 30)
        recent = expenses.filter(pl.col("date") >= cutoff)

        if recent.is_empty():
            recent = expenses  # fallback: usa tudo disponível

        actual_months = max(self._count_months(recent), 1)
        monthly_avg = float(recent["amount"].sum()) * -1 / actual_months
        monthly_avg = max(monthly_avg, 0.0)

        predicted = round(monthly_avg, 2)
        lower = round(predicted * (1 - _FALLBACK_CI_FACTOR), 2)
        upper = round(predicted * (1 + _FALLBACK_CI_FACTOR), 2)

        return SpendPrediction(
            category=category,
            predicted_spend=predicted,
            lower_bound=lower,
            upper_bound=upper,
            method="moving_average",
            months_of_data=months,
            reference_date=ref,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────────────

    def _filter_expenses(
        self,
        df: pl.DataFrame,
        category: str | None,
    ) -> pl.DataFrame:
        """Filtra despesas (amount < 0), opcionalmente por categoria."""
        if "date" not in df.columns or "amount" not in df.columns:
            return pl.DataFrame()

        expenses = df.filter(pl.col("amount") < 0)

        if category is not None:
            if "category" not in expenses.columns:
                return pl.DataFrame()
            expenses = expenses.filter(pl.col("category") == category)

        return expenses

    def _count_months(self, df: pl.DataFrame) -> int:
        """Conta meses distintos no DataFrame."""
        if df.is_empty() or "date" not in df.columns:
            return 0
        return (
            df
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .select("ym")
            .unique()
            .height
        )

    def _empty_prediction(self, category: str, ref: date) -> SpendPrediction:
        return SpendPrediction(
            category=category,
            predicted_spend=0.0,
            lower_bound=0.0,
            upper_bound=0.0,
            method="moving_average",
            months_of_data=0,
            reference_date=ref,
        )
