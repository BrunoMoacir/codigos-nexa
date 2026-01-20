from fastapi import APIRouter
from app.integrations.open_finance.pluggy import PluggyClient

router = APIRouter(prefix="/pluggy", tags=["Pluggy Sandbox"])


@router.get("/auth-test")
def test_pluggy_auth():
    pluggy = PluggyClient()
    token = pluggy.authenticate()

    return {
        "status": "success",
        "access_token_preview": token[:20] + "..."
    }


@router.post("/sandbox-test")
def test_pluggy_sandbox():
    pluggy = PluggyClient()

    # 1. cria item sandbox
    item = pluggy.create_sandbox_item()
    item_id = item["id"]

    # 2. busca contas
    accounts = pluggy.get_accounts(item_id)

    transactions = {}

    # 3. busca transações se existir conta
    if accounts.get("results"):
        account_id = accounts["results"][0]["id"]
        transactions = pluggy.get_transactions(account_id)

    # 4. retorna JSON bruto (para você estudar o padrão)
    return {
        "item": item,
        "accounts": accounts,
        "transactions": transactions,
    }
