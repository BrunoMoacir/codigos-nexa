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

        # Alguns endpoints aceitam X-API-KEY (v1) e outros pedem Authorization: Bearer.
        # Enviamos ambos para compatibilidade.
        return {
            "X-API-KEY": self.access_token,
            "Authorization": f"Bearer {self.access_token}",
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

    def create_sandbox_item(
        self,
        clientUserId: str | None = None,
        perf_multiplier: int | None = None,
    ) -> dict:
        url = f"{self.BASE_URL}/items"

        user_value = "user-ok"
        if perf_multiplier and perf_multiplier > 0:
            bounded = min(perf_multiplier, 5000)
            user_value = f"user-ok-perf-{bounded}x"

        payload: dict = {
            "connectorId": 0,
            "parameters": {
                "user": user_value,
                "password": "password-ok",
            },
        }
        if clientUserId:
            payload["clientUserId"] = clientUserId

        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=30,
        )

        response.raise_for_status()
        return response.json()

    def get_item(self, item_id: str) -> dict:
        """Estado atual do item (status UPDATING/UPDATED/LOGIN_ERROR/...).

        É por este endpoint que o sync sabe se o banco já entregou os dados —
        chamar /accounts antes de UPDATED devolve lista vazia.
        """
        url = f"{self.BASE_URL}/items/{item_id}"

        response = requests.get(
            url,
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

    def get_transactions(
        self,
        account_id: str,
        page: int | None = None,
        page_size: int | None = None,
    ) -> dict:
        """Uma página de transações da conta.

        A Pluggy pagina este endpoint (pageSize padrão 20, máximo 500) e
        devolve `totalPages` na resposta. Quem chama precisa percorrer as
        páginas — ver fetch_all_transactions() em app/pluggy_sync/runner.py.
        """
        url = f"{self.BASE_URL}/transactions"

        params: dict = {"accountId": account_id}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["pageSize"] = page_size

        response = requests.get(
            url,
            params=params,
            headers=self._headers(),
            timeout=20,
        )

        response.raise_for_status()
        return response.json()

    def get_investments(self, item_id: str) -> dict:
        url = f"{self.BASE_URL}/investments"

        response = requests.get(
            url,
            params={"itemId": item_id},
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    def get_loans(self, item_id: str) -> dict:
        url = f"{self.BASE_URL}/loans"

        response = requests.get(
            url,
            params={"itemId": item_id},
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()

    def get_financings(self, item_id: str) -> dict:
        url = f"{self.BASE_URL}/financings"

        response = requests.get(
            url,
            params={"itemId": item_id},
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()
        return response.json()
