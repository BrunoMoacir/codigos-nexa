from app.cashflow.safe_to_spend import calculate_safe_to_spend
from app.cashflow.projector import CashflowProjector

transactions = [
    {"amount": 7200},
    {"amount": -5300},
]

projector = CashflowProjector()
projection = projector.project(transactions, days=30)

result = calculate_safe_to_spend(projection, horizon_days=30)

print(result)
