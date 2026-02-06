"backend/app/agent/nodes/forecast.py"
from app.core.forecast import generate_daily_forecast, calculate_safe_to_spend

def forecast_node(state):
    forecast = generate_daily_forecast(
        state["transactions"],
        start_balance=state["transactions"]["amount"].sum() * -1
    )
    state["forecast"] = forecast
    state["safe_to_spend"] = calculate_safe_to_spend(forecast)
    return state
