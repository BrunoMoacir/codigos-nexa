import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

# Assume agent is accessible here
from app.agent.graph import build_financial_agent
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])

# Carrega o grafo do agente (pode demorar no primeiro boot)
agent_app = build_financial_agent()

class ChatRequest(BaseModel):
    user_id: str
    message: str
    
class ChatResponse(BaseModel):
    response: str
    
@router.post("/", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """
    Endpoint principal para conversar com a Inteligência Nexa.
    O LLM vai interpretar a mensagem, decidir se precisa chamar alguma Ferramenta (ex: Optimizer de Cartão)
    e retornar a resposta em linguagem natural.
    """
    logger.info(f"Recebida mensagem do usuário {request.user_id}: {request.message[:50]}...")
    
    try:
        inputs = {
            "messages": [HumanMessage(content=request.message)]
        }
        
        # Invocando o agent. (Em prod, deve-se habilitar memória entre mensagens!)
        config = {"configurable": {"thread_id": request.user_id}}
        
        result = agent_app.invoke(inputs, config=config)
        
        # A resposta final do LLM estará na última mensagem do state
        target_message = result["messages"][-1].content
        
        return ChatResponse(response=target_message)
        
    except Exception as e:
        logger.error(f"Erro no Agent Chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ocorreu um erro ao processar sua mensagem via IA.")
