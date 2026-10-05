"""
app/agent/memoria.py — o thread do checkpointer: como se nomeia e como se apaga.

Dois problemas moravam na mesma linha do router:

    thread_id = chat_request.session_id or chat_request.user_id

1. **`session_id` vem do corpo da requisição, sem validação.** Dois usuários
   que mandassem o mesmo valor — `"1"`, `"default"`, `"session-1"` — passavam a
   COMPARTILHAR o thread do checkpointer, e portanto o histórico que o agente
   relê a cada turno. Não precisa de injeção de prompt nenhuma: basta colidir
   uma string. Agora o thread é sempre prefixado pelo dono
   (`{user_id}::{session_id}`), então colisão entre contas é impossível.

2. **O apagamento LGPD não alcançava nada disso.** `privacy/service.py` limpa
   22 tabelas, `chat_messages` entre elas — mas o estado do agente guarda as
   perguntas do usuário E todo resultado de ferramenta (renda, saldo, tarifas,
   dívidas), sob o thread_id, fora do Postgres. `DELETE /chat/history` também
   não o tocava: o usuário "apagava a conversa" e o agente seguia respondendo
   com ela. Com o prefixo, os threads de um titular são enumeráveis.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SEPARADOR = "::"


def thread_id_de(user_id: str, session_id: Optional[str] = None) -> str:
    """
    Thread do checkpointer para (usuário, sessão).

    Sempre prefixado pelo dono: `session_id` é entrada do cliente e sem o
    prefixo dois usuários podem cair no mesmo thread.
    """
    if not user_id:
        raise ValueError("thread_id_de exige user_id")
    if not session_id:
        return user_id
    # O separador não pode aparecer no meio e criar ambiguidade de prefixo.
    return f"{user_id}{_SEPARADOR}{str(session_id).replace(_SEPARADOR, '_')}"


def _threads_do_usuario(checkpointer, user_id: str) -> list[str]:
    """
    Threads do titular: o base e todos os `user_id::*`.

    O prefixo existe justamente para tornar a enumeração possível. Cada backend
    responde de um jeito:
      - MemorySaver expõe o dicionário `storage`;
      - Postgres tem a tabela `checkpoints` — dá para varrer por prefixo;
      - Redis não permite varrer sem SCAN, então resta o que já se conhece.
    """
    prefixo = f"{user_id}{_SEPARADOR}"
    conhecidos = {user_id}

    storage = getattr(checkpointer, "storage", None)
    if isinstance(storage, dict):
        conhecidos |= {t for t in storage if t == user_id or str(t).startswith(prefixo)}

    conhecidos |= _threads_no_postgres(checkpointer, user_id, prefixo)
    return sorted(conhecidos)


def _threads_no_postgres(checkpointer, user_id: str, prefixo: str) -> set[str]:
    """
    Varre a tabela `checkpoints` por `user_id` e `user_id::*`.

    Sem isto, um titular que conversou em várias sessões teria só o thread base
    apagado — e o resto do histórico (perguntas dele e todo retorno de
    ferramenta) sobreviveria à eliminação do art. 18 VI.
    """
    pool = getattr(checkpointer, "conn", None)
    if pool is None or not hasattr(pool, "connection"):
        return set()
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT thread_id FROM checkpoints"
                " WHERE thread_id = %s OR thread_id LIKE %s",
                (user_id, prefixo.replace("%", r"\%") + "%"),
            )
            linhas = cur.fetchall()
        return {
            (linha["thread_id"] if isinstance(linha, dict) else linha[0])
            for linha in linhas
        }
    except Exception as exc:
        logger.warning("[Agent] não foi possível enumerar threads no Postgres: %s", exc)
        return set()


def esquecer_conversas(user_id: str, session_id: Optional[str] = None) -> dict:
    """
    Apaga o estado do agente para o titular. Nunca levanta exceção.

    Com `session_id`, apaga SÓ o thread dessa sessão — é o "apagar esta
    conversa" do app. Sem ele, apaga todas (é o caminho da eliminação LGPD).

    Returns:
        `{"threads": [...], "apagados": int, "metodo": str, "erro": str|None}`

    Limitação declarada: em backends que não permitem enumerar threads (Redis,
    sem varredura por prefixo), apagamos o thread base e os que este processo
    conhece. Sessões nomeadas por outro processo e ainda não vistas aqui podem
    sobreviver até o próximo restart. Por isso o prefixo é a parte importante:
    ele torna a enumeração possível quando o backend suportar.
    """
    resultado: dict = {"threads": [], "apagados": 0, "metodo": "nenhum", "erro": None}
    try:
        from app.agent.singleton import get_agent

        checkpointer = getattr(get_agent(), "checkpointer", None)
        if checkpointer is None:
            resultado["erro"] = "agente sem checkpointer"
            return resultado

        threads = (
            [thread_id_de(user_id, session_id)] if session_id
            else _threads_do_usuario(checkpointer, user_id)
        )
        resultado["threads"] = threads

        # 1) API nativa, quando a versão do langgraph oferece
        if hasattr(checkpointer, "delete_thread"):
            resultado["metodo"] = "delete_thread"
            for thread in threads:
                try:
                    checkpointer.delete_thread(thread)
                    resultado["apagados"] += 1
                except Exception as exc:
                    logger.warning("[Agent] delete_thread(%s) falhou: %s", thread, exc)
            return resultado

        # 2) MemorySaver: storage[thread_id] e writes[(thread_id, ns, ck)]
        storage = getattr(checkpointer, "storage", None)
        writes = getattr(checkpointer, "writes", None)
        if isinstance(storage, dict):
            resultado["metodo"] = "storage"
            for thread in threads:
                if storage.pop(thread, None) is not None:
                    resultado["apagados"] += 1
            if isinstance(writes, dict):
                alvo = set(threads)
                for chave in [k for k in writes if isinstance(k, tuple) and k and k[0] in alvo]:
                    writes.pop(chave, None)
            return resultado

        resultado["erro"] = (
            f"checkpointer {type(checkpointer).__name__} não expõe forma de apagar thread"
        )
        logger.error("[Agent] Não foi possível esquecer conversas de %s: %s",
                     user_id, resultado["erro"])
        return resultado

    except Exception as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"
        logger.error("[Agent] esquecer_conversas(%s) falhou: %s", user_id, exc, exc_info=True)
        return resultado


__all__ = ["thread_id_de", "esquecer_conversas"]
