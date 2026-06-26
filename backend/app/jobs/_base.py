"""
app/jobs/_base.py — Utilitários compartilhados entre jobs.

Fornece:
  get_active_user_ids()  Lista de user_ids com transações nos últimos 30 dias.
  job_guard()            Decorator que loga start/end/erro e impede re-entrada concorrente.
"""

import asyncio
import logging
from datetime import date, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

_running_jobs: set[str] = set()


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
    - Impede execução concorrente do mesmo job (re-entrada).
    - Loga duração e eventuais erros sem deixar o scheduler travar.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if job_id in _running_jobs:
                logger.warning("[Job:%s] Já está rodando — pulando esta execução.", job_id)
                return
            _running_jobs.add(job_id)
            import time
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
                _running_jobs.discard(job_id)
        return wrapper
    return decorator
