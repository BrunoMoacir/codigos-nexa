# app/api/v1/routes/pluggy.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import logging
import requests as http_requests
import uuid

from sqlalchemy.orm import Session

from app.integrations.open_finance.pluggy import PluggyClient
from app.core.security import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.pluggy_item import PluggyItem

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pluggy", "Open Finance"])

class ConnectTokenResponse(BaseModel):
    connect_token: str

@router.post("/connect-token", response_model=ConnectTokenResponse, summary="Gera um Connect Token para o Widget")
def create_connect_token(current_user_str: str = Depends(get_current_user)):
    """Gera um connect_token obrigatório para inicializar o Widget Pluggy no Frontend."""
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

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
def list_user_items(
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna os items conectados do usuário.

    Observação: a Pluggy vem retornando 401 no GET /items (listagem) em alguns tenants,
    mas GET /items/{id} funciona. Mantemos dados reais persistindo os item_ids no DB.
    """
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    try:
        pluggy = PluggyClient()

        # Tentativa 1: listagem nativa da Pluggy (se estiver liberada)
        resp = http_requests.get(
            f"{settings.PLUGGY_BASE_URL}/items",
            params={"clientUserId": str(current_user_str)},
            headers=pluggy._headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()

        # Tentativa 2 (fallback real): buscar item_ids persistidos e resolver via /items/{id}
        if resp.status_code == 401:
            rows = (
                db.query(PluggyItem)
                .filter(PluggyItem.user_id == str(current_user_str))
                .all()
            )
            results = []
            for row in rows:
                r = http_requests.get(
                    f"{settings.PLUGGY_BASE_URL}/items/{row.item_id}",
                    headers=pluggy._headers(),
                    timeout=15,
                )
                if r.status_code == 200:
                    results.append(r.json())
                else:
                    logger.warning(
                        "Pluggy /items/%s returned %s: %s",
                        row.item_id,
                        r.status_code,
                        r.text,
                    )
            return {"results": results, "total": len(results)}

        logger.warning("Pluggy /items returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pluggy /items falhou ({resp.status_code}). {resp.text}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar items Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}",
        )


@router.post("/sandbox", summary="Cria um Item de Sandbox para testes")
def create_sandbox_item(
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria uma conexão fake (Sandbox) com a Pluggy Bank para testes de desenvolvimento."""
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    try:
        pluggy = PluggyClient()
        result = pluggy.create_sandbox_item(clientUserId=str(current_user_str))

        item_id = None
        connector_name = None
        if isinstance(result, dict):
            item_id = result.get("id")
            connector = result.get("connector") or {}
            connector_name = connector.get("name") if isinstance(connector, dict) else None

        if item_id:
            record = PluggyItem(
                id=str(uuid.uuid4()),
                user_id=str(current_user_str),
                item_id=str(item_id),
                connector_name=connector_name,
            )
            try:
                db.add(record)
                db.commit()
            except Exception:
                db.rollback()

        return {"success": True, "item": result}
    except Exception as e:
        logger.error(f"Erro ao criar sandbox item Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar sandbox: {str(e)}",
        )
