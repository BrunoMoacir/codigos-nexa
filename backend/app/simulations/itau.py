def mock_itau():
    # JSON no formato "nativo" do Itaú (simulado)
    return {
        "lancamentos": [
            {
                "descricao": "PIX RECEBIDO",
                "valor": 2000,
                "data": "2026-01-05"
            },
            {
                "descricao": "FARMACIA",
                "valor": -120.75,
                "data": "2026-01-07"
            }
        ]
    }


def map_itau(raw):
    # Converte para o padrão interno do sistema
    return [
        {
            "description": item["descricao"],
            "amount": item["valor"],
            "date": item["data"],
            "bank": "itau"
        }
        for item in raw["lancamentos"]
    ]
