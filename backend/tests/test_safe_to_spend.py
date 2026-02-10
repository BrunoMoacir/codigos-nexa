import polars as pl

from app.cashflow.safe_to_spend import SafeToSpendCalculator


def test_safe_to_spend():
    calc = SafeToSpendCalculator()

    df = pl.DataFrame({
        "date": ["2026-02-01", "2026-02-02", "2026-02-03"],
        "projected_balance": [2000, 1800, 1500],
        "expenses": [300, 200, 250]
    })

    result = calc.calculate(df, horizon_days=3)

    assert result.safe_to_spend_total > 0
    assert result.risk_level in {"LOW", "MEDIUM", "HIGH"}
