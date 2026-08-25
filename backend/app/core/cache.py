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
import time
from typing import Optional

import redis as redis_lib

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Parâmetros de infraestrutura que NÃO fazem parte da chave de cache ────────
_SKIP_KWARGS = {"db", "current_user", "request"}

# ── Singleton do cliente Redis ────────────────────────────────────────────────
_redis_client: Optional[redis_lib.Redis] = None
# Cooldown de 30s após falha: evita reconectar a cada request mas permite
# recuperar automaticamente quando o Redis voltar.
_REDIS_RETRY_COOLDOWN = 30.0
_redis_retry_after: float = 0.0  # timestamp Unix; 0 = nunca falhou


def _urls_a_tentar() -> list[str]:
    """
    URLs de Redis a tentar, em ordem.

    Em DESENVOLVIMENTO, quando `REDIS_URL` aponta para o hostname do
    docker-compose (`redis://redis:...`) e o processo não está num container, o
    nome não resolve e todo o Redis some — inclusive a **blacklist de tokens**.
    Medido em 2026-08-25: `get_redis()` devolvia None, `_is_token_revoked`
    devolvia False para tudo, logout não revogava e o reuso de refresh (que a
    doc chama de "indício de vazamento") não era detectado. E havia um Redis
    rodando em localhost o tempo todo.

    O fallback vale SÓ fora de produção: em produção, um Redis que não resolve
    é incidente e tem de aparecer como tal, não ser contornado.
    """
    urls = [settings.REDIS_URL]
    if settings.APP_ENV != "production" and "://redis:" in settings.REDIS_URL:
        urls.append(settings.REDIS_URL.replace("://redis:", "://127.0.0.1:"))
    return urls


def get_redis() -> Optional[redis_lib.Redis]:
    global _redis_client, _redis_retry_after

    ultimo_erro: Exception | None = None

    # Cliente já conectado e saudável
    if _redis_client is not None:
        return _redis_client

    # Dentro do cooldown pós-falha — não tenta reconectar ainda
    if time.monotonic() < _redis_retry_after:
        return None

    for url in _urls_a_tentar():
        try:
            client = redis_lib.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            _redis_client = client
            _redis_retry_after = 0.0
            if url != settings.REDIS_URL:
                logger.info(
                    "[Cache] Redis conectado em %s (REDIS_URL=%s não resolve fora do "
                    "docker). Fallback de DESENVOLVIMENTO apenas.",
                    url, settings.REDIS_URL,
                )
            else:
                logger.info("[Cache] Redis conectado: %s", url)
            return _redis_client
        except Exception as e:
            ultimo_erro = e

    _redis_client = None
    _redis_retry_after = time.monotonic() + _REDIS_RETRY_COOLDOWN
    logger.warning(
        "[Cache] Redis indisponível (%s) — retry em %.0fs. "
        "Sem Redis, a revogação de token fica em fail-open: logout não revoga "
        "e reuso de refresh não é detectado.",
        ultimo_erro, _REDIS_RETRY_COOLDOWN,
    )
    return _redis_client


def _on_redis_error(e: Exception) -> None:
    """Chamado quando uma operação Redis falha após a conexão já ter sido estabelecida."""
    global _redis_client, _redis_retry_after
    logger.warning("[Cache] Erro em operação Redis (%s) — desconectando e agendando retry.", e)
    _redis_client = None
    _redis_retry_after = time.monotonic() + _REDIS_RETRY_COOLDOWN


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
        _on_redis_error(e)
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
                        _on_redis_error(e)

                result = await func(*args, **kwargs)

                client = get_redis()  # re-obtém após possível reconexão
                if client:
                    try:
                        payload = result if isinstance(result, (str, int, float, bool)) else (
                            result.model_dump() if hasattr(result, "model_dump") else result
                        )
                        client.setex(cache_key, ttl, json.dumps(payload, default=str))
                        logger.debug("[Cache] SET  %s (ttl=%ds)", cache_key, ttl)
                    except Exception as e:
                        _on_redis_error(e)

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
                        _on_redis_error(e)

                result = func(*args, **kwargs)

                client = get_redis()  # re-obtém após possível reconexão
                if client:
                    try:
                        payload = result if isinstance(result, (str, int, float, bool)) else (
                            result.model_dump() if hasattr(result, "model_dump") else result
                        )
                        client.setex(cache_key, ttl, json.dumps(payload, default=str))
                        logger.debug("[Cache] SET  %s (ttl=%ds)", cache_key, ttl)
                    except Exception as e:
                        _on_redis_error(e)

                return result
            return sync_wrapper
    return decorator
