# app/etl/runner.py

"""
Runner principal do pipeline ETL.

Responsável por:
- Executar a coleta de dados
- Normalizar transações
- Preparar os dados para consumo pelos módulos de análise

Este módulo é o ponto central de ingestão de dados financeiros.
"""

from typing import Dict, Any, List
from datetime import datetime

from app.etl.transactions import fetch_transactions
from app.etl.normalize import normalize_transactions


def run_full_etl_pipeline(user_id: str) -> Dict[str, Any]:
    """
    Executa todo o pipeline ETL para um usuário.

    Fluxo:
        1. Busca transações brutas
        2. Normaliza dados
        3. Estrutura output padronizado

    Retorna:
        Dict contendo:
            - transactions
            - metadata
    """

    # 1. Busca transações brutas
    raw_transactions = fetch_transactions(user_id)

    # 2. Normaliza as transações
    normalized_transactions = normalize_transactions(raw_transactions)

    # 3. Empacota resposta final
    return {
        "transactions": normalized_transactions,
        "metadata": {
            "user_id": user_id,
            "generated_at": datetime.utcnow().isoformat(),
            "transactions_count": len(normalized_transactions),
        }
    }
