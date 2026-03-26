"""
Testa integração direta com a Pluggy (mock).

Objetivo:
    Garantir que:
        - O sandbox item é criado
        - A conta é retornada
        - As transações são obtidas

Este teste valida APENAS a integração externa.
"""

from app.core.integrations.pluggy_mock import MockPluggyClient


def test_pluggy_mock_flow():
    pluggy = MockPluggyClient()

    # Cria sandbox item
    item = pluggy.create_sandbox_item()
    assert "id" in item

    # Busca contas
    accounts = pluggy.get_accounts(item["id"])
    assert len(accounts["results"]) > 0

    # Busca transações
    account_id = accounts["results"][0]["id"]
    txs = pluggy.get_transactions(account_id)

    assert "results" in txs
    assert len(txs["results"]) > 0

    print("\n✅ Pluggy Mock Integration OK")
