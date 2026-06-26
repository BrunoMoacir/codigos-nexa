"""
app/jobs/_base.py — Utilitários compartilhados entre jobs.

Fornece:
  get_active_user_ids()  Lista de user_ids com transações nos últimos 30 dias.
  job_guard()            Decorator que impede re-entrada via lock distribuído Redis
                         (com fallback em memória se Redis estiver indisponível) e
                         loga start/end/erro sem deixar o scheduler travar.

Lock distribuído:
  Chave Redis: nexa:job_lock:{job_id}
  TTL: 2h — garante liberação automática mesmo se o processo morrer.
  Usa SET NX EX (atômico) — seguro em ambiente multi-worker/Railway.
"""

import logging
import time
from datetime import date, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

_JOB_LOCK_TTL = 7200        # 2 horas em segundos
_LOCK_PREFIX = "nexa:job_lock:"

# Fallback em memória para quando Redis não está disponível
_local_running: set[str] = set()


def _acquire_lock(job_id: str) -> bool:
    """
    Tenta adquirir o lock distribuído no Redis.
    Retorna True se obteve o lock, False se já existe (outro worker rodando).
    Fallback para lock em memória se Redis falhar.
    """
    try:
        from app.core.cache import get_redis
        redis = get_redis()
        if redis:
            acquired = redis.set(
                f"{_LOCK_PREFIX}{job_id}",
                "1",
                nx=True,   # só seta se NÃO existir (atômico)
                ex=_JOB_LOCK_TTL,
            )
            return bool(acquired)
    except Exception as exc:
        logger.warning("[job_guard:%s] Redis indisponível, usando lock local: %s", job_id, exc)

    # Fallback local
    if job_id in _local_running:
        return False
    _local_running.add(job_id)
    return True


def _release_lock(job_id: str) -> None:
    """Libera o lock distribuído e o fallback local."""
    try:
        from app.core.cache import get_redis
        redis = get_redis()
        if redis:
            redis.delete(f"{_LOCK_PREFIX}{job_id}")
    except Exception:
        pass
    _local_running.discard(job_id)


def get_active_user_ids() -> list[str]:
    """
    Retorna user_ids com atividade nos últimos 30 dias via DuckDB.
    Fallback para lista vazia se DuckDB não estiver disponível.
    """
    try:
        from app.core.db.queries import get_connection

        cutoff = (date.today() - timedelta(days=30)).isoformat()
        con = get_connection()
        try:
            rows = con.execute(
                "SELECT DISTINCT user_id FROM transactions_clean WHERE date >= ?",
                [cutoff],
            ).fetchall()
        finally:
            con.close()
        return [r[0] for r in rows]
    except Exception as exc:
        logger.warning("[jobs._base] Não foi possível obter usuários ativos: %s", exc)
        return []


def job_guard(job_id: str):
    """
    Decorator que:
    - Impede execução concorrente via lock distribuído Redis (multi-worker safe).
    - Fallback para lock em memória se Redis estiver indisponível.
    - Loga duração e eventuais erros sem deixar o scheduler travar.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not _acquire_lock(job_id):
                logger.warning("[Job:%s] Lock não obtido — já está rodando em outro worker.", job_id)
                return
            start = time.monotonic()
            try:
                logger.info("[Job:%s] Iniciando", job_id)
                await fn(*args, **kwargs)
                elapsed = time.monotonic() - start
                logger.info("[Job:%s] Concluído em %.1fs", job_id, elapsed)
            except Exception as exc:
                elapsed = time.monotonic() - start
                logger.error("[Job:%s] Erro após %.1fs: %s", job_id, elapsed, exc, exc_info=True)
            finally:
                _release_lock(job_id)
        return wrapper
    return decorator
