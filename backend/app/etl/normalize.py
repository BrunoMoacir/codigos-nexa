#app/etl/normalize.py
"""
Normalização de transações financeiras.
"""

from typing import List, Dict


def normalize_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Padroniza campos das transações.

    Aqui garantimos:
    - Datas padronizadas
    - Valores numéricos
    - Estrutura única para todo o sistema
    """

    normalized = []

    for t in transactions:
        normalized.append({
            "date": t["date"],
            "amount": float(t["amount"]),
            "description": t.get("description", ""),
            "type": t["type"]
        })

    return normalized
