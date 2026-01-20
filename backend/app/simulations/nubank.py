def mock_nubank():
    return {
        "transactions": [
            {
                "title": "Salário",
                "amount": 3500,
                "created_at": "2026-01-03"
            },
            {
                "title": "Uber",
                "amount": -45.90,
                "created_at": "2026-01-04"
            }
        ]
    }


def map_nubank(raw):
    return [
        {
            "description": t["title"],
            "amount": t["amount"],
            "date": t["created_at"],
            "bank": "nubank"
        }
        for t in raw["transactions"]
    ]
