# app/api/v1/routes/pluggy.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import logging
import requests as http_requests

from app.integrations.open_finance.pluggy import PluggyClient
from app.core.security import get_current_user
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pluggy", "Open Finance"])

class ConnectTokenResponse(BaseModel):
    connect_token: str

@router.post("/connect-token", response_model=ConnectTokenResponse, summary="Gera um Connect Token para o Widget")
def create_connect_token(current_user_str: str = Depends(get_current_user)):
    """Gera um connect_token obrigatório para inicializar o Widget Pluggy no Frontend."""
    try:
        user_identifier = str(current_user_str)
        logger.info(f"Gerando connect-token para banco do usuário {user_identifier}")
        
        pluggy = PluggyClient()
        connect_token = pluggy.create_connect_token(clientUserId=user_identifier)
        
        token_str = ""
        if isinstance(connect_token, dict):
            token_str = connect_token.get("accessToken", connect_token.get("connectToken", ""))
        elif hasattr(connect_token, "accessToken"):
            token_str = connect_token.accessToken
        else:
            token_str = str(connect_token)

        if not token_str:
             raise Exception("Token inválido retornado pelo SDK da Pluggy")

        return ConnectTokenResponse(connect_token=token_str)
        
    except Exception as e:
        logger.error(f"Erro ao gerar connect token Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}"
        )


@router.get("/items", summary="Lista os Items (contas bancárias) conectados do usuário")
def list_user_items(current_user_str: str = Depends(get_current_user)):
    """
    Retorna os items (conexões bancárias) do usuário logado via clientUserId.
    """
    try:
        pluggy = PluggyClient()
        pluggy.authenticate()
        
        # Pluggy permite filtrar items pelo clientUserId
        resp = http_requests.get(
            f"{settings.PLUGGY_BASE_URL}/items",
            params={"clientUserId": str(current_user_str)},
            headers=pluggy._headers(),
            timeout=15,
        )
        
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning(f"Pluggy /items returned {resp.status_code}: {resp.text}")
            return {"results": [], "total": 0}
            
    except Exception as e:
        logger.error(f"Erro ao listar items Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}"
        )


@router.post("/sandbox", summary="Cria um Item de Sandbox para testes")
def create_sandbox_item(current_user_str: str = Depends(get_current_user)):
    """Cria uma conexão fake (Sandbox) com a Pluggy Bank para testes de desenvolvimento."""
    try:
        pluggy = PluggyClient()
        result = pluggy.create_sandbox_item()
        return {"success": True, "item": result}
    except Exception as e:
        logger.error(f"Erro ao criar sandbox item Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar sandbox: {str(e)}"
        )
