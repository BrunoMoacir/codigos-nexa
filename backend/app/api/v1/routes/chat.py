import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List

from app.agent.graph import build_financial_agent
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.security import get_current_user
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])
limiter = Limiter(key_func=get_remote_address)

# Carrega o grafo do agente (pode demorar no primeiro boot)
agent_app = build_financial_agent()


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_with_agent(
    request: Request,
    chat_request: ChatRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Endpoint principal para conversar com a Inteligência Nexa.
    O LLM vai interpretar a mensagem, decidir se precisa chamar alguma Ferramenta
    e retornar a resposta em linguagem natural.
    """
    if chat_request.user_id != current_user:
        raise HTTPException(status_code=403, detail="Não autorizado (token não pertence a este user_id)")

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

        result = agent_app.invoke(inputs, config=config)

        # A resposta final do LLM estará na última mensagem do state
        target_message = result["messages"][-1].content

        return ChatResponse(response=target_message)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Erro no Agent Chat: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Erro IA: {str(e)}")
