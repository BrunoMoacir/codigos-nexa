import polars as pl
from datetime import date, timedelta

from app.cashflow.safe_to_spend import calculate_safe_to_spend

# Simular projeção de 30 dias
dates = [date.today() + timedelta(days=i) for i in range(30)]

projection_df = pl.DataFrame({
    "date": dates,
    "projected_balance": [
        3800 - (i * 120) for i in range(30)
    ],
    "expenses": [
        -96.67 for _ in range(30)
    ]
})

result = calculate_safe_to_spend(
    projection_df=projection_df,
    horizon_days=30
)

print("\n📊 SAFE TO SPEND RESULT\n")
print(result)
print("\nComo dict:")
print(result.to_dict())
