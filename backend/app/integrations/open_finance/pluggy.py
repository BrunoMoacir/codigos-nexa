#app/integrations/open_finance/pluggy.py
import logging
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class PluggyClient:
    """
    Cliente responsável por conversar com a API da Pluggy
    """

    BASE_URL = settings.PLUGGY_BASE_URL

    def __init__(self):
        self.client_id = settings.PLUGGY_CLIENT_ID
        self.client_secret = settings.PLUGGY_CLIENT_SECRET
        self.access_token: str | None = None

    def authenticate(self) -> str:
        url = f"{self.BASE_URL}/auth"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        payload = {
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
        }

        response = requests.post(
            url,
            data=payload,   # 👈 form-urlencoded
            headers=headers,
            timeout=10,
        )

        logger.debug("Pluggy auth status: %s", response.status_code)

        response.raise_for_status()

        data = response.json()

        if "apiKey" not in data:
            raise Exception(f"Resposta inesperada da Pluggy: {data}")

        self.access_token = data["apiKey"]
        return self.access_token

    def _headers(self) -> dict:
        if not self.access_token:
            self.authenticate()

        return {
            "X-API-KEY": self.access_token, # Pluggy v1 auth header
            "Content-Type": "application/json",
        }

    def create_connect_token(self, clientUserId: str) -> dict:
        url = f"{self.BASE_URL}/connect_token"

        payload = {
            "clientUserId": clientUserId,
            "options": {
                "clientCustomColor": "#6366f1",
                "clientCustomName": "Nexa Finance"
            }
        }

        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    def create_sandbox_item(self) -> dict:
        url = f"{self.BASE_URL}/items"

        payload = {
            "connectorId": "pluggy_sandbox",
            "parameters": {
                "username": "user_ok",
                "password": "password_ok",
            },
        }

        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    def get_accounts(self, item_id: str) -> dict:
        url = f"{self.BASE_URL}/accounts"

        response = requests.get(
            url,
            params={"itemId": item_id},
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    def get_transactions(self, account_id: str) -> dict:
        url = f"{self.BASE_URL}/transactions"

        response = requests.get(
            url,
            params={"accountId": account_id},
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()
