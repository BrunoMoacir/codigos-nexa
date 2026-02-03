import polars as pl
from app.cashflow import SafeToSpendCalculator


def test_safe_to_spend_90d():
    cashflow = pl.DataFrame({
        "date": pl.date_range(
            start=pl.datetime(2026, 3, 21),
            end=pl.datetime(2026, 6, 18),
            interval="1d",
            eager=True
        ),
        "starting_balance": [14519.4] * 90,
        "expenses": [0.0] * 89 + [49.9],
        "projected_balance": [14519.4] * 89 + [14469.5],
    })

    calculator = SafeToSpendCalculator(buffer=1000.0)
    result = calculator.calculate(cashflow, days=90)

    print("\n💸 SAFE TO SPEND (90 DIAS)")
    for k, v in result.items():
        print(f"{k}: {v}")

    assert result["safe_to_spend_daily"] > 0
    assert result["min_projected_balance"] == 14469.5


if __name__ == "__main__":
    test_safe_to_spend_90d()
