from app.analysis.recurring_detector import RecurringDetector

detector = RecurringDetector()

transactions = [
    {"date": "2025-01-01", "description": "Netflix", "amount": -39.9},
    {"date": "2025-02-01", "description": "Netflix", "amount": -39.9},
    {"date": "2025-03-01", "description": "Netflix", "amount": -39.9},
]

print(detector.run(transactions))