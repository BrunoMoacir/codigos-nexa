import requests  # Biblioteca HTTP
from app.core.config import settings  # Configurações do projeto


class PluggyClient:
    """
    Cliente responsável por conversar com a API da Pluggy
    """

    BASE_URL = "https://api.pluggy.ai"  # URL base da Pluggy

    def __init__(self):
        # Lê o clientId do .env
        self.client_id = settings.PLUGGY_CLIENT_ID

        # Lê o clientSecret do .env
        self.client_secret = settings.PLUGGY_CLIENT_SECRET

        # Token que será obtido após autenticação
        self.access_token: str | None = None

    def authenticate(self) -> str:
        """
        Realiza autenticação na Pluggy e retorna o access_token
        """

        # Endpoint de autenticação da Pluggy
        url = f"{self.BASE_URL}/auth"

        # Corpo da requisição (body params)
        payload = {
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
        }

        # Requisição POST para a Pluggy
        response = requests.post(
            url,
            json=payload,      # Envia como JSON
            timeout=10         # Timeout de segurança
        )

        # Se a resposta não for 200, algo deu errado
        if response.status_code != 200:
            raise Exception(
                f"Erro ao autenticar na Pluggy: {response.status_code} - {response.text}"
            )

        # Converte resposta JSON em dicionário
        data = response.json()

        # Guarda o token em memória
        self.access_token = data["accessToken"]

        # Retorna o token
        return self.access_token
