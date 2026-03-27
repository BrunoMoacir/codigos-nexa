import logging
from fastapi import APIRouter, HTTPException, Depends, Request, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from app.agent.graph import build_financial_agent
from app.agent.models import ChatMessage
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.security import get_current_user
from app.core.config import settings
from app.core.database import get_db
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])
limiter = Limiter(key_func=get_remote_address)

_agent_app = None

def _get_agent():
    global _agent_app
    if _agent_app is None:
        _agent_app = build_financial_agent()
    return _agent_app


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


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

    logger.info(f"Recebida mensagem do usuário {chat_request.user_id}: {chat_request.message[:50]}...")

    try:
        # Injetamos um SystemMessage com o ID do usuário para o LLM não precisar perguntar.
        inputs = {
            "messages": [
                SystemMessage(content=f"[SYSTEM HIDDEN CONTEXT] O ID interno deste usuário é '{chat_request.user_id}'. ASSUMA este user_id ao chamar QUALQUER ferramenta de dados."),
                HumanMessage(content=chat_request.message)
            ]
        }

        # O thread_id agrupa o histórico na memória do agente
        config = {"configurable": {"thread_id": chat_request.user_id}}

        result = _get_agent().invoke(inputs, config=config)

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

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Erro no Agent Chat: {e}\n{tb}")
        raise HTTPException(status_code=503, detail=f"Erro IA: {str(e)}")


@router.get("/history", response_model=List[ChatHistoryItem])
def get_chat_history(
    user_id: str = Query(..., description="ID do usuário"),
    limit: int = Query(50, ge=1, le=200, description="Número máximo de mensagens"),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retorna o histórico de mensagens do usuário, ordenado do mais antigo ao mais recente.
    """
    if current_user != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

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
