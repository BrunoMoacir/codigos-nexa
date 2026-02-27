import logging
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from app.core.config import settings

# Import the new tool for F2
from app.agent.tools.get_card_optimization import get_card_optimization

logger = logging.getLogger(__name__)

def build_financial_agent():
    """
    Constrói o agente LangGraph usando um modelo pré-construído ReAct.
    Este agente é capaz de "raciocinar" e invocar ferramentas iterativamente
    baseado na pergunta do usuário.
    """
    # 1. Lista de ferramentas disponíveis (Skills)
    tools = [get_card_optimization]
    
    # 2. Inicializa o LLM (O Cérebro)
    # Requer langchain-openai e a chave no .env
    from langchain_openai import ChatOpenAI
    
    if not settings.OPENAI_API_KEY:
        logger.warning("[Agent] OPENAI_API_KEY não configurada! O agente VAI falhar ao ser chamado se não estiver no teste unitário mockado.")
        llm = ChatOpenAI(api_key="mock", model="gpt-4o-mini") # Placeholder to not break instantiation
    else:
        llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY, 
            model="gpt-4o-mini", 
            temperature=0.0
        )
    
    # 3. Prompt do Sistema
    system_message = (
        "Você é o Nexa, um assistente de inteligência financeira corporativa de alto nível.\n"
        "Seu objetivo é dar conselhos precisos sobre como o usuário pode otimizar as próprias finanças.\n\n"
        "Quando perguntado sobre 'qual cartão de crédito obter', você DEVE SEMPRE:\n"
        "1. Obter a renda mensal (monthly_income) ou os gastos mensais (safe_to_spend) do usuário conversionalmente SE NÃO foram informados logo de cara.\n"
        "2. Chamar a ferramenta `get_card_optimization` passando estes parâmetros junto com o `user_id`.\n"
        "3. Interpretar o output da ferramenta e devolver o resultado de forma clara, natural e elegante. Jamais despeje dados brutos de programação (como JSON)."
    )
    
    # 4. Cria o Agente ReAct
    # langgraph.prebuilt.create_react_agent faz o trabalho pesado de amarrar o StateGraph de chat sozinho!
    # Nota: Em LangGraph 1.0.9+ usamos 'prompt' para o system prompt
    app = create_react_agent(llm, tools=tools, prompt=system_message)
    
    return app
