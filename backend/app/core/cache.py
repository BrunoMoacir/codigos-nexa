"""
app/core/cache.py — Redis cache decorator para endpoints FastAPI.

Uso:
    @cache_response(prefix="forecast", ttl=900)
    async def get_forecast(user_id: str, ...):
        ...

A chave de cache é construída com base em todos os parâmetros do endpoint,
exceto os de infraestrutura (db, current_user, request).

Se o Redis estiver indisponível, a função é chamada normalmente (cache desativado
de forma transparente — sem exceções).
"""

import json
import logging
import functools
import asyncio
from typing import Optional

import redis as redis_lib

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Parâmetros de infraestrutura que NÃO fazem parte da chave de cache ────────
_SKIP_KWARGS = {"db", "current_user", "request"}

# ── Singleton do cliente Redis ────────────────────────────────────────────────
_redis_client: Optional[redis_lib.Redis] = None
_redis_failed = False  # evita reconectar a cada request após falha inicial


def get_redis() -> Optional[redis_lib.Redis]:
    global _redis_client, _redis_failed
    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        client = redis_lib.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        _redis_client = client
        logger.info("[Cache] Redis conectado: %s", settings.REDIS_URL)
    except Exception as e:
        logger.warning("[Cache] Redis indisponível (%s) — cache desativado.", e)
        _redis_failed = True
    return _redis_client


def invalidate_user_cache(user_id: str) -> int:
    """Remove todas as entradas de cache de um usuário. Retorna quantas foram removidas."""
    client = get_redis()
    if not client:
        return 0
    try:
        keys = client.keys(f"nexa:cache:*:user_id={user_id}*")
        if keys:
            return client.delete(*keys)
    except Exception as e:
        logger.warning("[Cache] Erro ao invalidar cache do user %s: %s", user_id, e)
    return 0


# Versão do schema de cache. Incrementar aqui invalida todas as entradas
# antigas automaticamente, sem precisar esperar o TTL expirar.
_CACHE_VERSION = "v1"


def _build_key(prefix: str, kwargs: dict) -> str:
    parts = sorted(
        f"{k}={v}" for k, v in kwargs.items()
        if k not in _SKIP_KWARGS and v is not None
    )
    return f"nexa:cache:{_CACHE_VERSION}:{prefix}:" + ":".join(parts)


def cache_response(prefix: str, ttl: int = 900):
    """
    Decorator que cacheia a resposta de um endpoint no Redis.

    Args:
        prefix: identificador do endpoint (ex: "forecast", "budget")
        ttl: tempo de vida em segundos (padrão: 15 minutos)
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                cache_key = _build_key(prefix, kwargs)
                client = get_redis()
                if client:
                    try:
                        cached = client.get(cache_key)
                        if cached is not None:
                            logger.debug("[Cache] HIT  %s", cache_key)
                            return json.loads(cached)
                    except Exception as e:
                        logger.warning("[Cache] Erro ao ler: %s", e)

                result = await func(*args, **kwargs)

                if client:
                    try:
                        payload = result if isinstance(result, (str, int, float, bool)) else (
                            result.model_dump() if hasattr(result, "model_dump") else result
                        )
                        client.setex(cache_key, ttl, json.dumps(payload, default=str))
                        logger.debug("[Cache] SET  %s (ttl=%ds)", cache_key, ttl)
                    except Exception as e:
                        logger.warning("[Cache] Erro ao salvar: %s", e)

                return result
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                cache_key = _build_key(prefix, kwargs)
                client = get_redis()
                if client:
                    try:
                        cached = client.get(cache_key)
                        if cached is not None:
                            logger.debug("[Cache] HIT  %s", cache_key)
                            return json.loads(cached)
                    except Exception as e:
                        logger.warning("[Cache] Erro ao ler: %s", e)

                result = func(*args, **kwargs)

                if client:
                    try:
                        payload = result if isinstance(result, (str, int, float, bool)) else (
                            result.model_dump() if hasattr(result, "model_dump") else result
                        )
                        client.setex(cache_key, ttl, json.dumps(payload, default=str))
                        logger.debug("[Cache] SET  %s (ttl=%ds)", cache_key, ttl)
                    except Exception as e:
                        logger.warning("[Cache] Erro ao salvar: %s", e)

                return result
            return sync_wrapper
    return decorator
