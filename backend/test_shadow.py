from app.core.shadow_invoices import detect_shadow_invoices

transactions = [
    {"date": "2025-01-01", "description": "Spotify", "amount": -29.9},
    {"date": "2025-02-01", "description": "Spotify", "amount": -29.9},
    {"date": "2025-03-01", "description": "Spotify", "amount": -29.9},
]

print(detect_shadow_invoices(transactions))
