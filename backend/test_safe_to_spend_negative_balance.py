import polars as pl
from app.cashflow import SafeToSpendCalculator


def test_safe_to_spend_negative_balance():
    cashflow = pl.DataFrame({
        "date": pl.date_range(
            start=pl.datetime(2026, 3, 21),
            end=pl.datetime(2026, 4, 19),
            interval="1d",
            eager=True
        ),
        "starting_balance": [1000.0] * 30,
        "expenses": [0.0] * 29 + [900.0],
        "projected_balance": [1000.0] * 29 + [100.0],
    })

    calculator = SafeToSpendCalculator(buffer=500.0)
    result = calculator.calculate(cashflow, days=30)

    print("\n🚨 SAFE TO SPEND COM QUEBRA DE CAIXA")
    for k, v in result.items():
        print(f"{k}: {v}")

    assert result["safe_to_spend_daily"] == 0.0
    assert result["min_projected_balance"] == 100.0


if __name__ == "__main__":
    test_safe_to_spend_negative_balance()
