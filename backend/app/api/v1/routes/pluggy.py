# app/api/v1/routes/pluggy.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import logging

from app.integrations.open_finance.pluggy import PluggyClient
from app.core.security import get_current_user, TokenData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pluggy", "Open Finance"])

class ConnectTokenResponse(BaseModel):
    connect_token: str

@router.post("/connect-token", response_model=ConnectTokenResponse, summary="Gera um Connect Token para o Widget")
def create_connect_token(current_user_str: str = Depends(get_current_user)):
    """
    Gera um `connect_token` obrigatório para inicializar o Widget JavaScript
    da Pluggy no Frontend. Este token tem validade curta (geralmente 30 mins)
    e atrela a conta bancária conectada a este Item do usuário (clientUserId).
    """
    try:
        # get_current_user retorna uma string user_id ou email em algumas implementações
        user_identifier = str(current_user_str)
        
        logger.info(f"Gerando connect-token para banco do usuário {user_identifier}")
        
        # Inicia cliente oficial da Pluggy
        pluggy = PluggyClient()
        
        # A própria documentação da Pluggy pede para criar o connect_token atrelado ao usuário
        # Em python SDK oficial é diferente, mas aqui nós abstraímos na nossa classe `PluggyClient`
        connect_token = pluggy.create_connect_token(clientUserId=user_identifier)
        
        # Em versões antigas do SDK pode retornar um dict ou dict-like com accessToken
        token_str = ""
        if isinstance(connect_token, dict):
            token_str = connect_token.get("accessToken", connect_token.get("connectToken", ""))
        elif hasattr(connect_token, "accessToken"):
            token_str = connect_token.accessToken
        elif hasattr(connect_token, "get"):
            token_str = connect_token.get("accessToken", "")
        else:
            token_str = str(connect_token) # Fallback primitivo

        if not token_str:
             raise Exception("Token inválido retornado pelo SDK da Pluggy")

        return ConnectTokenResponse(connect_token=token_str)
        
    except Exception as e:
        logger.error(f"Erro ao gerar connect token Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}"
        )
