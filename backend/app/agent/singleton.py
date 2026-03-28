"""
app/agent/singleton.py — Singleton thread-safe do agente LLM financeiro.

Centraliza a instância do agente para evitar que agent/router.py e
api/v1/routes/analyze.py criem instâncias duplicadas com seus próprios
locks independentes.

Uso:
    from app.agent.singleton import get_agent
    agent = get_agent()
    result = agent.invoke(inputs, config=config)
"""

import threading
import logging

from app.agent.graph import build_financial_agent

logger = logging.getLogger(__name__)

_agent = None
_agent_lock = threading.Lock()


def get_agent():
    """
    Retorna a instância singleton do agente LLM.

    Double-checked locking garante inicialização única mesmo com múltiplas
    requisições simultâneas no startup.
    """
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                logger.info("[Agent] Inicializando agente LLM financeiro...")
                _agent = build_financial_agent()
                logger.info("[Agent] Agente inicializado com sucesso.")
    return _agent
