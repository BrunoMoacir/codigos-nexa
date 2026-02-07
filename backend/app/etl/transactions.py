#app/etl/transactions.py
"""
Módulo responsável por buscar transações financeiras.
"""

from typing import List, Dict


def fetch_transactions(user_id: str) -> List[Dict]:
    """
    Mock temporário de coleta de transações.

    Depois será substituído por:
        - Pluggy
        - Open Finance
        - Bancos diretos

    Retorna lista de transações.
    """

    return [
        {"date": "2025-01-01", "amount": 7200, "type": "credit", "description": "Salário"},
        {"date": "2025-01-05", "amount": -1200, "type": "debit", "description": "Aluguel"},
        {"date": "2025-01-10", "amount": -800, "type": "debit", "description": "Cartão crédito"},
        {"date": "2025-01-15", "amount": -1500, "type": "debit", "description": "Fatura cartão"},
    ]
