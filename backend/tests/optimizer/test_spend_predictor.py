# tests/optimizer/test_spend_predictor.py
# Testes para T3.2 — SpendPredictor

from __future__ import annotations

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import polars as pl

from app.ml.spend_predictor import SpendPrediction, SpendPredictor


# ─── Helpers ────────────────────────────────────────────────────────────────────

REF = date(2026, 4, 24)

_SCHEMA = {
    "date": pl.Date,
    "amount": pl.Float64,
    "category": pl.Utf8,
}


def _txns(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=_SCHEMA)


def _months_of_txns(
    n_months: int,
    monthly_spend: float = -1000.0,
    category: str = "Alimentação",
    ref: date = REF,
) -> pl.DataFrame:
    """Gera n_months meses de transações com gasto mensal fixo."""
    rows = []
    for m in range(n_months, 0, -1):
        txn_date = ref - timedelta(days=m * 30)
        rows.append({"date": txn_date, "amount": monthly_spend, "category": category})
    return _txns(rows)


@pytest.fixture
def predictor():
    return SpendPredictor()


# ─── Testes: SpendPrediction dataclass ──────────────────────────────────────────

class TestSpendPrediction:
    def test_confidence_interval_property(self):
        pred = SpendPrediction(
            category="total",
            predicted_spend=1000.0,
            lower_bound=800.0,
            upper_bound=1200.0,
            method="moving_average",
            months_of_data=3,
            reference_date=REF,
        )
        assert pred.confidence_interval == (800.0, 1200.0)

    def test_frozen_dataclass_immutable(self):
        pred = SpendPrediction(
            category="total",
            predicted_spend=500.0,
            lower_bound=400.0,
            upper_bound=600.0,
            method="moving_average",
            months_of_data=2,
            reference_date=REF,
        )
        with pytest.raises((AttributeError, TypeError)):
            pred.predicted_spend = 999.0  # type: ignore


# ─── Testes: DataFrame vazio e None ─────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_dataframe_returns_zero_prediction(self, predictor):
        empty = pl.DataFrame(schema=_SCHEMA)
        result = predictor.predict_next_30d(empty, reference_date=REF)
        assert result.predicted_spend == 0.0
        assert result.method == "moving_average"
        assert result.months_of_data == 0

    def test_none_dataframe_returns_zero_prediction(self, predictor):
        result = predictor.predict_next_30d(None, reference_date=REF)
        assert result.predicted_spend == 0.0

    def test_no_expenses_only_income_returns_zero(self, predictor):
        income_only = _txns([
            {"date": REF - timedelta(days=10), "amount": 5000.0, "category": "Renda"},
            {"date": REF - timedelta(days=40), "amount": 5000.0, "category": "Renda"},
        ])
        result = predictor.predict_next_30d(income_only, reference_date=REF)
        assert result.predicted_spend == 0.0

    def test_category_not_in_data_returns_zero(self, predictor):
        df = _months_of_txns(3, category="Alimentação")
        result = predictor.predict_next_30d(df, category="Transporte", reference_date=REF)
        assert result.predicted_spend == 0.0
        assert result.category == "Transporte"

    def test_missing_category_column_for_filtered_category(self, predictor):
        df = pl.DataFrame(
            {"date": [REF - timedelta(days=15)], "amount": [-500.0]},
            schema={"date": pl.Date, "amount": pl.Float64},
        )
        result = predictor.predict_next_30d(df, category="Alimentação", reference_date=REF)
        assert result.predicted_spend == 0.0

    def test_result_category_label_preserved(self, predictor):
        df = _months_of_txns(2, category="Lazer")
        result = predictor.predict_next_30d(df, category="Lazer", reference_date=REF)
        assert result.category == "Lazer"

    def test_total_category_label_when_none(self, predictor):
        df = _months_of_txns(2)
        result = predictor.predict_next_30d(df, category=None, reference_date=REF)
        assert result.category == "total"


# ─── Testes: fallback moving average ────────────────────────────────────────────

class TestMovingAverage:
    def test_uses_moving_average_with_less_than_6_months(self, predictor):
        df = _months_of_txns(3, monthly_spend=-1000.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.method == "moving_average"

    def test_predicted_spend_close_to_monthly_avg(self, predictor):
        # 3 meses × R$1000/mês → previsão ≈ R$1000
        df = _months_of_txns(3, monthly_spend=-1000.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert 800.0 <= result.predicted_spend <= 1200.0

    def test_confidence_interval_is_20_percent_around_predicted(self, predictor):
        df = _months_of_txns(3, monthly_spend=-1000.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.lower_bound == pytest.approx(result.predicted_spend * 0.80, abs=1.0)
        assert result.upper_bound == pytest.approx(result.predicted_spend * 1.20, abs=1.0)

    def test_lower_bound_never_negative(self, predictor):
        df = _months_of_txns(1, monthly_spend=-10.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.lower_bound >= 0.0

    def test_months_of_data_reported_correctly(self, predictor):
        df = _months_of_txns(4, monthly_spend=-500.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.months_of_data == 4

    def test_uses_moving_average_when_prophet_not_installed(self, predictor):
        df = _months_of_txns(8, monthly_spend=-2000.0)
        with patch.object(predictor, "_prophet_predict", side_effect=ImportError("prophet not installed")):
            result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.method == "moving_average"

    def test_uses_moving_average_when_prophet_raises_exception(self, predictor):
        df = _months_of_txns(7, monthly_spend=-1500.0)
        with patch.object(predictor, "_prophet_predict", side_effect=RuntimeError("fit failed")):
            result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.method == "moving_average"

    def test_reference_date_stored_in_result(self, predictor):
        df = _months_of_txns(2)
        custom_ref = date(2026, 3, 1)
        result = predictor.predict_next_30d(df, reference_date=custom_ref)
        assert result.reference_date == custom_ref

    def test_predicted_spend_non_negative(self, predictor):
        df = _months_of_txns(2, monthly_spend=-50.0)
        result = predictor.predict_next_30d(df, reference_date=REF)
        assert result.predicted_spend >= 0.0


# ─── Testes: seleção de método (Prophet vs moving_average) ──────────────────────

class TestMethodSelection:
    def test_6_months_triggers_prophet_attempt(self, predictor):
        df = _months_of_txns(6, monthly_spend=-1000.0)
        with patch.object(predictor, "_prophet_predict") as mock_prophet:
            mock_prophet.return_value = SpendPrediction(
                category="total", predicted_spend=1000.0,
                lower_bound=800.0, upper_bound=1200.0,
                method="prophet", months_of_data=6, reference_date=REF,
            )
            result = predictor.predict_next_30d(df, reference_date=REF)
        mock_prophet.assert_called_once()
        assert result.method == "prophet"

    def test_5_months_does_not_trigger_prophet(self, predictor):
        df = _months_of_txns(5, monthly_spend=-1000.0)
        with patch.object(predictor, "_prophet_predict") as mock_prophet:
            predictor.predict_next_30d(df, reference_date=REF)
        mock_prophet.assert_not_called()

    def test_prophet_result_returned_when_successful(self, predictor):
        df = _months_of_txns(8, monthly_spend=-2000.0)
        expected = SpendPrediction(
            category="total", predicted_spend=2100.0,
            lower_bound=1800.0, upper_bound=2400.0,
            method="prophet", months_of_data=8, reference_date=REF,
        )
        with patch.object(predictor, "_prophet_predict", return_value=expected):
            result = predictor.predict_next_30d(df, reference_date=REF)
        assert result is expected


# ─── Testes: predict_by_category ────────────────────────────────────────────────

class TestPredictByCategory:
    def test_always_includes_total(self, predictor):
        df = _months_of_txns(3, category="Alimentação")
        results = predictor.predict_by_category(df, reference_date=REF)
        assert "total" in results

    def test_returns_prediction_for_each_qualifying_category(self, predictor):
        rows = []
        ref = REF
        for m in range(3, 0, -1):
            d = ref - timedelta(days=m * 30)
            rows.append({"date": d, "amount": -1000.0, "category": "Alimentação"})
            rows.append({"date": d, "amount": -500.0,  "category": "Transporte"})
        df = _txns(rows)

        results = predictor.predict_by_category(df, min_monthly_spend=100.0, reference_date=REF)
        assert "Alimentação" in results
        assert "Transporte" in results

    def test_min_monthly_spend_filters_low_categories(self, predictor):
        rows = []
        ref = REF
        for m in range(3, 0, -1):
            d = ref - timedelta(days=m * 30)
            rows.append({"date": d, "amount": -1000.0, "category": "Alimentação"})
            rows.append({"date": d, "amount": -10.0, "category": "Lazer"})  # R$10/mês
        df = _txns(rows)

        results = predictor.predict_by_category(df, min_monthly_spend=100.0, reference_date=REF)
        assert "Alimentação" in results
        assert "Lazer" not in results

    def test_no_category_column_returns_only_total(self, predictor):
        df = pl.DataFrame(
            {"date": [REF - timedelta(days=30)], "amount": [-500.0]},
            schema={"date": pl.Date, "amount": pl.Float64},
        )
        results = predictor.predict_by_category(df, reference_date=REF)
        assert list(results.keys()) == ["total"]

    def test_all_values_are_spend_predictions(self, predictor):
        df = _months_of_txns(3, category="Alimentação")
        results = predictor.predict_by_category(df, reference_date=REF)
        for v in results.values():
            assert isinstance(v, SpendPrediction)

    def test_empty_df_returns_only_total_with_zero(self, predictor):
        empty = pl.DataFrame(schema=_SCHEMA)
        results = predictor.predict_by_category(empty, reference_date=REF)
        assert results["total"].predicted_spend == 0.0
        assert len(results) == 1


# ─── Testes: _count_months helper ───────────────────────────────────────────────

class TestCountMonths:
    def test_single_month_returns_1(self, predictor):
        df = _txns([{"date": date(2026, 1, 15), "amount": -100.0, "category": "X"}])
        assert predictor._count_months(df) == 1

    def test_same_month_different_days_counts_as_1(self, predictor):
        df = _txns([
            {"date": date(2026, 1, 5),  "amount": -100.0, "category": "X"},
            {"date": date(2026, 1, 20), "amount": -200.0, "category": "X"},
        ])
        assert predictor._count_months(df) == 1

    def test_three_distinct_months(self, predictor):
        df = _txns([
            {"date": date(2026, 1, 10), "amount": -100.0, "category": "X"},
            {"date": date(2026, 2, 10), "amount": -100.0, "category": "X"},
            {"date": date(2026, 3, 10), "amount": -100.0, "category": "X"},
        ])
        assert predictor._count_months(df) == 3

    def test_empty_df_returns_0(self, predictor):
        empty = pl.DataFrame(schema=_SCHEMA)
        assert predictor._count_months(empty) == 0
