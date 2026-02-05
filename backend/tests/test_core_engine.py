import polars as pl
from datetime import date

from app.core.recurrence import detect_recurring_transactions
from app.core.forecast import generate_daily_forecast, calculate_safe_to_spend

def test_detect_recurring():
    df = pl.DataFrame({
        "date": [date(2024,1,1), date(2024,2,1), date(2024,3,1)],
        "description": ["Netflix", "Netflix", "Netflix"],
        "amount": [-39.9, -39.9, -39.9]
    })

    result = detect_recurring_transactions(df)
    assert result["is_recurring"].all()

def test_safe_to_spend_positive():
    df = pl.DataFrame({
        "date": [date.today()],
        "amount": [-100]
    })

    forecast = generate_daily_forecast(df, start_balance=1000)
    sts = calculate_safe_to_spend(forecast, buffer=0)

    assert sts["safe_to_spend_total"] > 0
    assert sts["safe_to_spend_daily"] > 0