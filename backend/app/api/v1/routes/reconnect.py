"""
app/api/v1/routes/reconnect.py - Endpoint para Reconectar Consentimento

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe POST /reconnect/{user_id} que:
    1. Chama Pluggy.create_connect_token() para obter token do Widget
    2. Retorna a URL de conexão para o frontend fazer redirect
    3. Callback POST /reconnect/{user_id}/callback salva o item_id no DB
       quando o usuário completa a conexão

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO DE RECONEXÃO                                                   ║
╚══════════════════════════════════════════════════════════════════════╝

POST /api/v1/reconnect/user_123
        ↓
PluggyClient.create_connect_token(user_id) → accessToken
        ↓
Retornar { "connect_url": "https://connect.pluggy.ai?accessToken=..." }
        ↓
Frontend faz redirect para connect_url
        ↓
Usuário conecta conta no Widget Pluggy
        ↓
POST /api/v1/reconnect/user_123/callback?connection_id=<item_id>
        ↓
Salva/atualiza PluggyItem no banco
        ↓
Webhook /transactions/webhook atualiza dados
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.integrations.pluggy import PluggyClient
from app.core.config import settings
from app.core.database import get_db
from app.core.models.pluggy_item import PluggyItem

router = APIRouter(prefix="/reconnect", tags=["Reconnect"])
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConnectUrlResponse(BaseModel):
    user_id: str = Field(..., description="ID do usuário")
    connect_url: str = Field(..., description="URL para redirecionar o usuário ao Widget Pluggy")
    expires_at: datetime = Field(..., description="Quando a sessão de conexão expira")
    redirect_back_uri: str = Field(..., description="URL de retorno após conexão")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_id": "user_123",
            "connect_url": "https://connect.pluggy.ai?accessToken=tok_abc123&redirectUrl=...",
            "expires_at": "2025-02-12T15:30:00Z",
            "redirect_back_uri": "https://nexa.app/dashboard"
        }
    })


class ReconnectRequest(BaseModel):
    redirect_uri: str | None = Field(
        None,
        description="URL para redirecionar após conexão (padrão: dashboard)"
    )


class CallbackResponse(BaseModel):
    status: str
    user_id: str
    connection_id: str
    timestamp: str
    message: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /reconnect/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{user_id}", response_model=ConnectUrlResponse)
async def create_reconnect_url(
    user_id: str,
    request: ReconnectRequest | None = None,
    current_user: str = Depends(get_current_user),
) -> ConnectUrlResponse:
    """
    Gera URL de reconexão para o usuário via Pluggy Connect Widget.

    **Quando usar:**
    - Consentimento está vencendo (T-7/T-0)
    - Usuário quer adicionar um novo banco
    - Conexão falhou e precisa reconectar

    **Fluxo no Frontend:**
    1. Receber `connect_url`
    2. Redirecionar usuário: `window.location.href = connect_url`
    3. Usuário conecta conta no Widget Pluggy
    4. Pluggy redireciona para `redirect_back_uri`
    5. Frontend chama `POST /reconnect/{user_id}/callback?connection_id=<item_id>`
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    redirect_uri = (request.redirect_uri if request else None) or f"{settings.FRONTEND_BASE_URL}/dashboard"

    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integração Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.",
        )

    try:
        logger.info("Gerando URL de reconexão para user_id=%s", user_id)

        pluggy = PluggyClient()
        token_response = pluggy.create_connect_token(clientUserId=user_id)

        access_token = token_response.get("accessToken")
        if not access_token:
            logger.error("Pluggy retornou resposta sem accessToken: %s", token_response)
            raise ValueError("accessToken ausente na resposta da Pluggy")

        # Monta a URL do Widget Pluggy Connect
        import urllib.parse
        connect_url = (
            f"{settings.PLUGGY_CONNECT_URL}"
            f"?accessToken={urllib.parse.quote(access_token)}"
            f"&redirectUrl={urllib.parse.quote(redirect_uri)}"
        )

        # Connect tokens expiram em 30 minutos (documentação Pluggy)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        logger.info("URL de conexão gerada para user_id=%s (expira em 30min)", user_id)

        return ConnectUrlResponse(
            user_id=user_id,
            connect_url=connect_url,
            expires_at=expires_at,
            redirect_back_uri=redirect_uri,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao gerar URL de reconexão para user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar URL de conexão. Tente novamente em alguns instantes.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /reconnect/{user_id}/callback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{user_id}/callback", response_model=CallbackResponse)
async def reconnect_callback(
    user_id: str,
    connection_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallbackResponse:
    """
    Chamado pelo frontend após o usuário concluir a conexão no Widget Pluggy.

    Salva (ou atualiza) o PluggyItem no banco para que o webhook de transações
    passe a sincronizar os dados desta conexão.

    **Parâmetros:**
    - `connection_id`: item_id retornado pelo Pluggy ao final da conexão
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if not connection_id or not connection_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="connection_id é obrigatório",
        )

    logger.info("Callback de reconexão: user_id=%s connection_id=%s", user_id, connection_id)

    try:
        # Verifica se já existe um item com esse item_id para este usuário
        existing = (
            db.query(PluggyItem)
            .filter(PluggyItem.user_id == user_id, PluggyItem.item_id == connection_id)
            .first()
        )

        if existing:
            # Já existe — apenas registra que reconexão foi confirmada
            logger.info(
                "PluggyItem já existe para user=%s item=%s — reconexão confirmada",
                user_id, connection_id,
            )
        else:
            # Novo item — persiste no banco
            new_item = PluggyItem(
                id=str(uuid.uuid4()),
                user_id=user_id,
                item_id=connection_id,
                connector_name=None,  # Atualizado pelo webhook quando disponível
            )
            db.add(new_item)
            db.commit()
            logger.info("Novo PluggyItem salvo: user=%s item=%s", user_id, connection_id)

    except Exception as e:
        db.rollback()
        logger.error(
            "Erro ao salvar PluggyItem para user=%s item=%s: %s",
            user_id, connection_id, e, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao registrar a conexão. Os dados serão sincronizados em breve.",
        )

    return CallbackResponse(
        status="success",
        user_id=user_id,
        connection_id=connection_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message="Conexão registrada! Os dados financeiros serão sincronizados em breve.",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", tags=["Health"])
async def reconnect_health():
    """Health check do serviço."""
    return {
        "status": "ok",
        "service": "reconnect",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
