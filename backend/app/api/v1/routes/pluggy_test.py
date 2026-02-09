# #app/api/v1/routes/pluggy_test
# from fastapi import APIRouter
# from app.integrations.open_finance.pluggy_mock import MockPluggyClient
# # futuramente: from app.integrations.open_finance.pluggy import PluggyClient

# router = APIRouter(prefix="/pluggy", tags=["Pluggy Sandbox"])


# @router.post("/sandbox-test")
# def test_pluggy_sandbox():
#     pluggy = MockPluggyClient()

#     item = pluggy.create_sandbox_item()
#     item_id = item["id"]

#     accounts = pluggy.get_accounts(item_id)

#     transactions = {}
#     if accounts.get("results"):
#         account_id = accounts["results"][0]["id"]
#         transactions = pluggy.get_transactions(account_id)

#     return {
#         "item": item,
#         "accounts": accounts,
#         "transactions": transactions,
#     }
