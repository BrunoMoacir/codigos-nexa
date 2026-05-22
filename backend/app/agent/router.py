import asyncio
import logging
import threading
from fastapi import APIRouter, HTTPException, Depends, Request, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from app.agent.models import ChatMessage
from app.agent.singleton import get_agent as _get_agent
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.security import get_current_user, require_owner
from app.core.config import settings
from app.core.database import get_db
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])
limiter = Limiter(key_func=get_remote_address)

# Singleton do agente LLM importado do módulo centralizado (app.agent.singleton)
# para evitar instâncias duplicadas entre este router e api/v1/routes/analyze.py


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str


class ChatClearResponse(BaseModel):
    deleted_count: int


class ChatHistoryItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_with_agent(
    request: Request,
    chat_request: ChatRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Endpoint principal para conversar com a Inteligência Nexa.
    O LLM vai interpretar a mensagem, decidir se precisa chamar alguma Ferramenta
    e retornar a resposta em linguagem natural.
    """
    if chat_request.user_id != current_user:
        raise HTTPException(status_code=403, detail="Não autorizado (token não pertence a este user_id)")

    # Em dev, evita 500 quando LLM não está configurado
    if settings.LLM_PROVIDER == "openai" and (not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "mock"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM (OpenAI) não configurado. Defina OPENAI_API_KEY no backend/.env para usar o chat.",
        )
    if settings.LLM_PROVIDER == "anthropic" and (not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "mock"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM (Anthropic) não configurado. Defina ANTHROPIC_API_KEY no backend/.env para usar o chat.",
        )

    logger.info("Mensagem recebida de user_id=%s (len=%d)", chat_request.user_id, len(chat_request.message))

    try:
        # Injeta o user_id autenticado como contexto imutável do sistema.
        # IMPORTANTE: este valor vem do token JWT verificado, não do input do usuário.
        # O LLM deve usar EXCLUSIVAMENTE este user_id em todas as chamadas de ferramenta,
        # ignorando qualquer user_id que apareça na mensagem do usuário.
        inputs = {
            "messages": [
                HumanMessage(content=(
                    f"[user_id autenticado: {chat_request.user_id}] "
                    f"Use SOMENTE este user_id em todas as ferramentas.\n\n"
                    f"{chat_request.message}"
                ))
            ]
        }

        # O thread_id agrupa o histórico na memória do agente.
        # Se a UI fornecer session_id, ele permite reiniciar a conversa sem
        # perder o histórico persistido por usuário.
        thread_id = chat_request.session_id or chat_request.user_id
        config = {"configurable": {"thread_id": thread_id}}

        # Executa o agente em thread pool com timeout de 60s para não bloquear workers
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: _get_agent().invoke(inputs, config=config)
                ),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout no agente LLM para user_id=%s", chat_request.user_id)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Tempo limite excedido. Tente novamente.",
            )

        # A resposta final do LLM estará na última mensagem do state
        messages = result.get("messages", [])
        if not messages:
            raise ValueError("Agente retornou lista de mensagens vazia")
        target_message = messages[-1].content

        # Persistir a mensagem do usuário e a resposta do agente
        db.add(ChatMessage(user_id=chat_request.user_id, role="human", content=chat_request.message))
        db.add(ChatMessage(user_id=chat_request.user_id, role="assistant", content=target_message))
        db.commit()

        return ChatResponse(response=target_message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro no Agent Chat para user_id=%s: %s", chat_request.user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Erro interno ao processar sua mensagem.",
        )


@router.get("/history", response_model=List[ChatHistoryItem])
def get_chat_history(
    user_id: str = Depends(require_owner),
    limit: int = Query(50, ge=1, le=200, description="Número máximo de mensagens"),
    db: Session = Depends(get_db),
):
    """
    Retorna o histórico de mensagens do usuário, ordenado do mais antigo ao mais recente.
    """

    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    # Retornar em ordem cronológica (do mais antigo ao mais recente)
    rows = list(reversed(rows))

    return [
        ChatHistoryItem(
            id=row.id,
            role=row.role,
            content=row.content,
            created_at=str(row.created_at),
        )
        for row in rows
    ]


@router.delete("/history", response_model=ChatClearResponse)
def clear_chat_history(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ChatClearResponse:
    """Remove o histórico persistido do chat para o usuário autenticado."""

    deleted_count = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()

    logger.info("Historico de chat removido para user_id=%s | deleted=%d", user_id, deleted_count)
    return ChatClearResponse(deleted_count=deleted_count)
