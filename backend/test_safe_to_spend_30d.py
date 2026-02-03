import polars as pl
from app.cashflow import SafeToSpendCalculator


def test_safe_to_spend_30d():
    cashflow = pl.DataFrame({
        "date": pl.date_range(
            start=pl.datetime(2026, 3, 21),
            end=pl.datetime(2026, 4, 19),
            interval="1d",
            eager=True,
        ),
        "starting_balance": [14519.4] * 30,
        "expenses": [0.0] * 29 + [49.9],
        "projected_balance": [14519.4] * 29 + [14469.5],
    })

    calculator = SafeToSpendCalculator(buffer=1000.0)
    result = calculator.calculate(cashflow, days=30)

    print("\n💸 SAFE TO SPEND (30 DIAS)")
    for k, v in result.items():
        print(f"{k}: {v}")

    assert result["safe_to_spend_daily"] > 0
    assert result["min_projected_balance"] == 14469.5


if __name__ == "__main__":
    test_safe_to_spend_30d()
