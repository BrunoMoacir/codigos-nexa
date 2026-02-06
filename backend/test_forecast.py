from app.domain.forecast_engine import ForecastEngine

engine = ForecastEngine()

result = engine.project_balance(
    current_balance=3800,
    daily_variable_spend=120,
    fixed_expenses=1800,
    subscriptions=320,
    installments=780,
    days=30
)

print(result)
