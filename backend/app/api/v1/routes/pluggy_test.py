from fastapi import APIRouter
from app.integrations.open_finance.pluggy import PluggyClient

router = APIRouter(prefix="/pluggy", tags=["Pluggy"])


@router.get("/auth-test")
def test_pluggy_auth():
    """
    Endpoint de teste para autenticação na Pluggy
    """

    # Cria o cliente da Pluggy
    pluggy = PluggyClient()

    # Executa a autenticação
    token = pluggy.authenticate()

    # Retorna parte do token (não tudo por segurança)
    return {
        "status": "success",
        "access_token_preview": token[:20] + "..."
    }
