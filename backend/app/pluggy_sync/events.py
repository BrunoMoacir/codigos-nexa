"""
app/pluggy_sync/events.py — Barramento de eventos in-process.

Quem publica: a thread que executa o job e o webhook da Pluggy.
Quem escuta:  as rotas de long-polling/SSE (asyncio) e o loop que espera o
              item ficar pronto dentro do job (thread bloqueante).

Escopo deliberado: um único processo. Com WEB_CONCURRENCY > 1 o worker que
atende o long-poll pode não ser o mesmo que roda o job — por isso todos os
esperadores também releem o estado do banco a cada `poll_interval`. O
barramento é a otimização (acorda na hora); o banco é a fonte da verdade.

Chaves usadas:
    job:{job_id}    → mudou o estado de um job
    item:{item_id}  → a Pluggy avisou algo sobre o item (webhook)
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict, Set

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_subscribers: Dict[str, Set["_Subscriber"]] = {}


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def item_key(item_id: str) -> str:
    return f"item:{item_id}"


class _Subscriber:
    """Base: registra/desregistra a si mesmo em uma chave do barramento."""

    def __init__(self, key: str) -> None:
        self.key = key

    def notify(self) -> None:  # pragma: no cover - implementado nas subclasses
        raise NotImplementedError

    def __enter__(self) -> "_Subscriber":
        with _lock:
            _subscribers.setdefault(self.key, set()).add(self)
        return self

    def __exit__(self, *exc_info) -> None:
        with _lock:
            subs = _subscribers.get(self.key)
            if subs is not None:
                subs.discard(self)
                if not subs:
                    _subscribers.pop(self.key, None)


class AsyncSubscription(_Subscriber):
    """Assinatura para rotas async (long-polling e SSE)."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()

    def notify(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._event.set)
        except RuntimeError:
            # Loop já encerrado — o assinante está saindo de qualquer forma.
            pass

    async def wait(self, timeout: float) -> bool:
        """True se houve evento; False se estourou o timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        self._event.clear()
        return True


class ThreadSubscription(_Subscriber):
    """Assinatura para código bloqueante (a thread que executa o job)."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self._event = threading.Event()

    def notify(self) -> None:
        self._event.set()

    def wait(self, timeout: float) -> bool:
        """True se houve evento; False se estourou o timeout."""
        if self._event.wait(timeout=timeout):
            self._event.clear()
            return True
        return False


def publish(key: str) -> None:
    """Acorda todos os assinantes de uma chave. Seguro de chamar de qualquer thread."""
    with _lock:
        subs = list(_subscribers.get(key, ()))
    for sub in subs:
        try:
            sub.notify()
        except Exception as e:  # nunca deixe um assinante quebrar o publisher
            logger.debug("[SyncEvents] Falha ao notificar %s: %s", key, e)


def subscriber_count(key: str) -> int:
    """Quantos esperadores existem nesta chave (usado em logs e testes)."""
    with _lock:
        return len(_subscribers.get(key, ()))
