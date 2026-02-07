from app.analysis.shadow_invoice_detector import ShadowInvoiceDetector

detector = ShadowInvoiceDetector()

transactions = [
    {"date": "2025-01-01", "description": "Spotify", "amount": -29.9},
    {"date": "2025-02-01", "description": "Spotify", "amount": -29.9},
    {"date": "2025-03-01", "description": "Spotify", "amount": -29.9},
]

print(detector.run(transactions))