# tests/opportunities/test_balance_store.py
"""
Round-trip real de account_balances (OPP4-E): payload estilo Pluggy (mock,
com poupança) → save_account_balances → get_latest_balance/by_bank.
Usa o banco de testes real (SessionLocal), mesmo padrão do teste de
integração do opportunity_engine.
"""
import uuid

import pytest

from app.core.database import Base, engine
from app.core.db.balances import (
    get_latest_balance,
    get_latest_balances_by_bank,
    save_account_balances,
)
from app.core.integrations.pluggy_mock import MockPluggyClient
from app.core.models.account_balance import AccountBalance


@pytest.fixture(autouse=True)
def _ensure_table():
    Base.metadata.create_all(bind=engine, tables=[AccountBalance.__table__])


@pytest.fixture
def user_id():
    return f"user_bal_{uuid.uuid4().hex[:8]}"


class TestRoundTrip:
    def test_payload_do_mock_persiste_corrente_e_poupanca(self, user_id):
        accounts = MockPluggyClient().get_accounts("item_test")["results"]
        assert save_account_balances(user_id, "item_test", accounts) == 2

        savings = get_latest_balance(user_id, "SAVINGS")
        checking = get_latest_balance(user_id, "CHECKING")
        assert savings is not None and savings.balance == 15_000.0
        assert savings.bank_name == "Nubank"
        assert checking is not None and checking.balance == 5_000.0

    def test_sync_novo_prevalece_sobre_o_antigo(self, user_id):
        accounts = MockPluggyClient().get_accounts("item_test")["results"]
        save_account_balances(user_id, "item_test", accounts)

        updated = [dict(a) for a in accounts]
        updated[1]["balance"] = 18_000.0
        save_account_balances(user_id, "item_test", updated)

        assert get_latest_balance(user_id, "SAVINGS").balance == 18_000.0

    def test_agregacao_por_banco_soma_contas_nao_credito(self, user_id):
        accounts = MockPluggyClient().get_accounts("item_test")["results"]
        save_account_balances(user_id, "item_test", accounts)
        by_bank = get_latest_balances_by_bank(user_id)
        assert by_bank.get("Nubank") == 20_000.0  # 5k corrente + 15k poupança

    def test_usuario_sem_snapshots_retorna_none(self):
        assert get_latest_balance("user_inexistente_xyz", "SAVINGS") is None
        assert get_latest_balances_by_bank("user_inexistente_xyz") == {}

    def test_conta_sem_balance_e_ignorada_sem_quebrar(self, user_id):
        accounts = [
            {"id": "a1", "type": "BANK", "subtype": "SAVINGS_ACCOUNT"},  # sem balance
            {"id": "a2", "type": "BANK", "subtype": "SAVINGS_ACCOUNT", "balance": "abc"},
            {"type": "BANK", "balance": 100.0},  # sem id
        ]
        assert save_account_balances(user_id, "item_test", accounts) == 0
