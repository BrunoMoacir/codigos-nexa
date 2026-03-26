"""
app/api/v1/routes/reconnect.py - Endpoint para Reconectar Consentimento

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe POST /reconnect/{user_id} que:
    1. Gera URL de conexão (Pluggy/Belvo)
    2. Retorna para o frontend fazer redirect
    3. Webhook atualiza o consentimento quando usuário conecta

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO DE RECONEXÃO                                                   ║
╚══════════════════════════════════════════════════════════════════════╝

POST /api/v1/reconnect/user_123
        ↓
Criar nova conexão na Pluggy/Belvo
        ↓
Retornar {
    "connect_url": "https://pluggy.io/open-finance/connections/..."
}
        ↓
Frontend faz redirect para connect_url
        ↓
Usuário conecta conta no Pluggy
        ↓
Webhook /transactions/webhook atualiza consentimento
        ↓
Dados começam a fluir novamente
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import get_current_user

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Pluggy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.core.integrations.pluggy import PluggyClient
from app.core.config import settings

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/reconnect", tags=["Reconnect"])
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConnectUrlResponse(BaseModel):
    """Resposta com URL de conexão"""
    user_id: str = Field(..., description="ID do usuário")
    connect_url: str = Field(..., description="URL para redirecionar o usuário")
    expires_at: datetime = Field(..., description="Quando a URL expira")
    redirect_back_uri: str = Field(..., description="URL for Pluggy redirect back")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_id": "user_123",
            "connect_url": "https://pluggy.io/open-finance/connections/...",
            "expires_at": "2025-02-12T15:30:00Z",
            "redirect_back_uri": "https://nexa.app/dashboard"
        }
    })


class ReconnectRequest(BaseModel):
    """Request body (opcional - parametros)"""
    redirect_uri: str | None = Field(
        None,
        description="URL para redirecionar após conexão (padrão: dashboard)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /reconnect/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{user_id}", response_model=ConnectUrlResponse)
async def create_reconnect_url(
    user_id: str,
    request: ReconnectRequest | None = None,
    current_user: str = Depends(get_current_user)
) -> ConnectUrlResponse:
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    """
    Gera URL de reconexão para o usuário.
    
    **Quando usar:**
    - Consentimento está vencendo (T-7/T-0)
    - Usuário quer adicionar um novo banco
    - Conexão falhou e precisa reconectar
    
    **O que retorna:**
    ```json
    {
        "user_id": "user_123",
        "connect_url": "https://pluggy.io/open-finance/connections/abc123",
        "expires_at": "2025-02-12T15:30:00Z",
        "redirect_back_uri": "https://nexa.app/dashboard"
    }
    ```
    
    **Fluxo no Frontend:**
    1. Receber `connect_url`
    2. Redirecionar usuário: `window.location.href = connect_url`
    3. Usuário conecta conta no Pluggy
    4. Pluggy redireciona para `redirect_back_uri`
    5. Dashboard atualiza com dados novos
    
    **Notas:**
    - URL válida por 24 horas
    - Usuário pode fechar a janela e voltar depois
    - Consentimento será atualizado ao conectar
    """
    
    try:
        logger.info(f"🔌 Gerando URL de reconexão para user_id={user_id}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Preparar parâmetros
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # URL para redirecionar após conexão
        redirect_uri = request.redirect_uri if request else None
        if not redirect_uri:
            redirect_uri = f"{settings.FRONTEND_BASE_URL}/dashboard"
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Chamar Pluggy para criar conexão
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        pluggy = PluggyClient()
        
        # TODO: Checar se PluggyClient tem método para gerar connect_url
        # Por enquanto, simulamos
        
        # Placeholder: Gerar URL fake (seria real em produção)
        from uuid import uuid4
        connection_id = str(uuid4())[:8]
        
        connect_url = f"https://pluggy.io/open-finance/connections/{connection_id}"
        
        logger.info(f"✅ URL gerada: {connect_url}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: TODO - Salvar no banco que reconexão foi iniciada
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # INSERT INTO reconnect_sessions (user_id, connection_id, created_at, expires_at)
        # VALUES (user_id, connection_id, NOW(), NOW() + interval 24 hours)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Retornar URL (valida por 24 horas)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Calcular expiração: agora + 24 horas
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        return ConnectUrlResponse(
            user_id=user_id,
            connect_url=connect_url,
            expires_at=expires_at,
            redirect_back_uri=redirect_uri
        )
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar URL de reconexão: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar URL: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /reconnect/{user_id}/callback (Webhook de retorno)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/{user_id}/callback")
async def reconnect_callback(
    user_id: str,
    connection_id: str,
    current_user: str = Depends(get_current_user)
):
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    """
    Webhook chamado pela Pluggy após usuário conectar.
    
    Este endpoint é chamado automaticamente pelo Pluggy quando:
    1. Usuário completa conexão na Pluggy
    2. Pluggy redireciona para `redirect_back_uri`
    3. Frontend chama este endpoint informando sucesso
    
    **Fluxo:**
    1. POST /reconnect/user_123/callback?connection_id=abc123
    2. Atualizar banco: SET reconnect_completed = true
    3. Próximo webhook /transactions/webhook atualizará dados
    
    TODO: Implementar isto com webhooks reais do Pluggy
    """
    
    logger.info(f"✅ Reconexão completa para user_id={user_id} (connection_id={connection_id})")
    
    # TODO: Atualizar no banco que reconexão foi completada
    # UPDATE items SET status = 'ACTIVE', consent_expires_at = ... WHERE connection_id = ?
    
    return {
        "status": "success",
        "user_id": user_id,
        "connection_id": connection_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Conexão atualizada! Os dados começarão a fluir em breve."
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", tags=["Health"])
async def reconnect_health():
    """Health check do serviço."""
    return {
        "status": "ok",
        "service": "reconnect",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
