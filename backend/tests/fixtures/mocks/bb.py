#backend/app/simulations/bb.py
def mock_bb():
    return {
        "movimentacoes": [
            {
                "historico": "TED RECEBIDA",
                "valor": 1800,
                "dataMovimento": "2026-01-02"
            },
            {
                "historico": "ENERGIA ELETRICA",
                "valor": -210,
                "dataMovimento": "2026-01-06"
            }
        ]
    }


def map_bb(raw):
    return [
        {
            "description": m["historico"],
            "amount": m["valor"],
            "date": m["dataMovimento"],
            "bank": "bb"
        }
        for m in raw["movimentacoes"]
    ]
