"""
app/pluggy_sync/service.py — Ciclo de vida do job de sync + long-polling + SSE.

    POST /pluggy/sync/jobs            → create_job() + start_job()  (202)
    GET  /pluggy/sync/jobs/{id}       → wait_for_job()   (long-polling com cursor)
    GET  /pluggy/sync/jobs/{id}/stream→ stream_job()     (SSE)

Regras que valem para os dois modos de acompanhamento:

  * O cursor é `version`, monotônico por job. O cliente manda o último que
    viu; se o job já avançou, a resposta sai na hora (sem corrida entre
    "terminei de ler" e "mudou de novo"). Se não avançou, a conexão fica
    pendurada até mudar ou até o timeout.
  * Todo esperador relê o banco periodicamente além de escutar o barramento
    in-process, para funcionar com múltiplos workers uvicorn.
  * Timeout de long-poll limitado a 30s: proxies (Railway) cortam conexões
    ociosas mais longas, e o SSE manda heartbeat a cada 15s pelo mesmo motivo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Iterator, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.models.pluggy_item import PluggyItem
from app.pluggy_sync import events
from app.pluggy_sync.models_orm import (
    JOB_ERROR,
    JOB_PARTIAL,
    JOB_PENDING,
    JOB_RUNNING,
    JOB_SUCCESS,
    JOB_TERMINAL,
    PHASE_DONE,
    PHASE_ERROR,
    PHASE_FETCHING,
    PHASE_PROCESSING,
    PHASE_QUEUED,
    PHASE_WAITING_BANK,
    PluggySyncJob,
)
from app.pluggy_sync.runner import ItemNotReady, sync_item_transactions, wait_item_ready

logger = logging.getLogger(__name__)

# Quanto tempo esperar cada item sair de UPDATING antes de desistir dele.
ITEM_READY_TIMEOUT = 180.0
# Fallback de reconsulta do status do item quando o webhook não chega.
ITEM_POLL_INTERVAL = 5.0

# Long-polling: teto por request (proxies cortam conexões ociosas longas).
MAX_LONG_POLL_TIMEOUT = 30.0
DEFAULT_LONG_POLL_TIMEOUT = 25.0
# Releitura do banco dentro do wait — cobre o caso multi-worker.
DB_POLL_INTERVAL = 1.5

# SSE
SSE_HEARTBEAT_INTERVAL = 15.0
SSE_MAX_DURATION = 900.0

# Job RUNNING sem atualização há mais que isso = worker morreu no meio.
STALE_AFTER = timedelta(minutes=15)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSÃO PRÓPRIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@contextmanager
def _session() -> Iterator[Session]:
    """Sessão independente da request.

    O job roda em outra thread e os esperadores releem o estado fora do
    ciclo do request — nenhum dos dois pode usar a Session do Depends.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normaliza datetimes do banco para UTC-aware (SQLite devolve naive)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SERIALIZAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def job_to_dict(job: PluggySyncJob) -> dict:
    try:
        detail = json.loads(job.detail) if job.detail else []
    except (TypeError, ValueError):
        detail = []

    created = _utc(job.created_at)
    updated = _utc(job.updated_at)
    finished = _utc(job.finished_at)

    return {
        "job_id": job.id,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        # Cursor a devolver no próximo long-poll / reconexão do SSE.
        "cursor": job.version,
        "done": job.status in JOB_TERMINAL,
        "items": {"total": job.items_total, "done": job.items_done},
        "totals": {
            "accounts": job.accounts,
            "received": job.received,
            "valid": job.valid,
            "saved": job.saved,
        },
        "detail": detail,
        "created_at": created.isoformat() if created else None,
        "updated_at": updated.isoformat() if updated else None,
        "finished_at": finished.isoformat() if finished else None,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEITURA / CRIAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_job(db: Session, job_id: str, user_id: str) -> Optional[PluggySyncJob]:
    """Job do usuário. Nunca retorna job de outro dono (IDOR)."""
    return (
        db.query(PluggySyncJob)
        .filter(PluggySyncJob.id == job_id, PluggySyncJob.user_id == str(user_id))
        .first()
    )


def get_job_state(job_id: str, user_id: str) -> Optional[dict]:
    """Estado serializado, lido em sessão própria (uso fora do request)."""
    with _session() as db:
        job = get_job(db, job_id, user_id)
        return job_to_dict(job) if job else None


def find_active_job(db: Session, user_id: str) -> Optional[PluggySyncJob]:
    """Job PENDING/RUNNING do usuário; marca como ERROR o que ficou órfão."""
    job = (
        db.query(PluggySyncJob)
        .filter(
            PluggySyncJob.user_id == str(user_id),
            PluggySyncJob.status.in_([JOB_PENDING, JOB_RUNNING]),
        )
        .order_by(PluggySyncJob.created_at.desc())
        .first()
    )
    if job is None:
        return None

    updated = _utc(job.updated_at) or _utc(job.created_at)
    if updated is not None and datetime.now(timezone.utc) - updated > STALE_AFTER:
        logger.warning("[PluggySync] Job %s órfão (sem update desde %s) — encerrando", job.id, updated)
        update_job(
            job.id,
            status=JOB_ERROR,
            phase=PHASE_ERROR,
            error="Sincronização interrompida (processo reiniciado). Tente novamente.",
            finished_at=datetime.now(timezone.utc),
        )
        return None

    return job


def list_jobs(db: Session, user_id: str, limit: int = 10) -> list[PluggySyncJob]:
    return (
        db.query(PluggySyncJob)
        .filter(PluggySyncJob.user_id == str(user_id))
        .order_by(PluggySyncJob.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )


def create_job(db: Session, user_id: str, item_ids: list[str]) -> PluggySyncJob:
    now = datetime.now(timezone.utc)
    job = PluggySyncJob(
        id=str(uuid.uuid4()),
        user_id=str(user_id),
        status=JOB_PENDING,
        phase=PHASE_QUEUED,
        progress=0,
        version=1,
        message=(
            f"{len(item_ids)} conexão(ões) na fila de sincronização."
            if item_ids else "Nenhuma conexão para sincronizar."
        ),
        items_total=len(item_ids),
        items_done=0,
        detail=json.dumps(
            [{"item_id": i, "status": JOB_PENDING, "saved": 0} for i in item_ids],
            ensure_ascii=False,
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def user_item_ids(db: Session, user_id: str) -> list[str]:
    rows = (
        db.query(PluggyItem)
        .filter(PluggyItem.user_id == str(user_id))
        .order_by(PluggyItem.created_at.asc())
        .all()
    )
    return [r.item_id for r in rows]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESCRITA (a única forma de mudar um job)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def update_job(job_id: str, **fields) -> Optional[dict]:
    """Aplica mudanças, incrementa o cursor e acorda os esperadores.

    Todo update passa por aqui: é o que garante que `version` nunca fica
    parado enquanto o estado muda (o long-poll ficaria pendurado até o
    timeout e o SSE nunca emitiria o evento).
    """
    detail = fields.pop("detail", None)
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)

    with _session() as db:
        job = db.query(PluggySyncJob).filter(PluggySyncJob.id == job_id).first()
        if job is None:
            return None

        for key, value in fields.items():
            setattr(job, key, value)
        if detail is not None:
            job.detail = detail

        job.version = (job.version or 0) + 1
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        state = job_to_dict(job)

    events.publish(events.job_key(job_id))
    return state


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def start_job(job_id: str, user_id: str) -> None:
    """Dispara o job numa thread daemon (não segura o worker do uvicorn)."""
    thread = threading.Thread(
        target=run_job,
        args=(job_id, str(user_id)),
        name=f"pluggy-sync-{job_id[:8]}",
        daemon=True,
    )
    thread.start()


def run_job(
    job_id: str,
    user_id: str,
    item_timeout: float = ITEM_READY_TIMEOUT,
    poll_interval: float = ITEM_POLL_INTERVAL,
) -> Optional[dict]:
    """Executa o sync do começo ao fim, publicando progresso a cada passo.

    Bloqueante por design (requests + ETL). Chamada direta em testes; em
    produção sempre via `start_job`.
    """
    from app.core.integrations.pluggy import PluggyClient

    with _session() as db:
        job = db.query(PluggySyncJob).filter(PluggySyncJob.id == job_id).first()
        if job is None:
            logger.warning("[PluggySync] Job %s não encontrado", job_id)
            return None
        try:
            detail = json.loads(job.detail) if job.detail else []
        except (TypeError, ValueError):
            detail = []
        item_ids = [entry.get("item_id") for entry in detail if entry.get("item_id")]

    if not item_ids:
        return update_job(
            job_id,
            status=JOB_SUCCESS,
            phase=PHASE_DONE,
            progress=100,
            message="Nenhuma conexão Pluggy para sincronizar.",
            finished_at=datetime.now(timezone.utc),
        )

    update_job(
        job_id,
        status=JOB_RUNNING,
        phase=PHASE_WAITING_BANK,
        progress=1,
        message="Falando com o banco...",
    )

    totals = {"accounts": 0, "received": 0, "valid": 0, "saved": 0}
    succeeded = 0
    failed = 0
    total_items = len(item_ids)

    for index, item_id in enumerate(item_ids):
        entry = detail[index]
        base_progress = int(100 * index / total_items)

        def publish(phase: str, message: str, extra_progress: int = 0, **entry_fields) -> None:
            entry.update(entry_fields)
            update_job(
                job_id,
                phase=phase,
                progress=min(99, base_progress + extra_progress),
                message=message,
                items_done=index,
                detail=detail,
                **totals,
            )

        pluggy = PluggyClient()

        # 1. Esperar o banco terminar de entregar os dados (item UPDATING).
        try:
            entry["status"] = JOB_RUNNING
            publish(PHASE_WAITING_BANK, "Aguardando o banco liberar os dados...", 5)

            def on_wait(item_status: Optional[str] = None, remaining: float = 0.0) -> None:
                publish(
                    PHASE_WAITING_BANK,
                    "Aguardando o banco liberar os dados...",
                    5,
                    item_status=item_status,
                )

            item_status = wait_item_ready(
                pluggy,
                item_id,
                timeout=item_timeout,
                poll_interval=poll_interval,
                on_progress=on_wait,
            )
            entry["item_status"] = item_status
        except ItemNotReady as e:
            failed += 1
            entry.update({"status": JOB_ERROR, "item_status": e.item_status, "error": e.message})
            publish(PHASE_WAITING_BANK, e.message, 5)
            continue
        except Exception as e:  # falha inesperada não pode matar os outros items
            failed += 1
            logger.error("[PluggySync] Erro esperando item %s: %s", item_id, e, exc_info=True)
            entry.update({"status": JOB_ERROR, "error": str(e)})
            publish(PHASE_WAITING_BANK, "Falha ao consultar a conexão.", 5)
            continue

        # 2. Baixar + processar.
        try:
            publish(PHASE_FETCHING, "Baixando transações...", 20)

            def on_sync(
                account_index: int = 0,
                accounts_total: int = 0,
                account_id: Optional[str] = None,
            ) -> None:
                if not accounts_total:
                    return
                share = int(60 * account_index / accounts_total / total_items)
                publish(
                    PHASE_PROCESSING,
                    f"Processando conta {account_index} de {accounts_total}...",
                    20 + share,
                    accounts_seen=account_index,
                )

            with _session() as work_db:
                report = sync_item_transactions(
                    db=work_db,
                    user_id=user_id,
                    item_id=item_id,
                    on_progress=on_sync,
                )

            for key in totals:
                totals[key] += report.get(key, 0)

            entry.update(
                {
                    "status": JOB_SUCCESS,
                    "accounts": report.get("accounts", 0),
                    "received": report.get("received", 0),
                    "valid": report.get("valid", 0),
                    "saved": report.get("saved", 0),
                    "errors": report.get("errors", []),
                }
            )
            succeeded += 1
            publish(
                PHASE_PROCESSING,
                f"{report.get('saved', 0)} transações sincronizadas.",
                90 // total_items,
            )
        except Exception as e:
            failed += 1
            logger.error("[PluggySync] Erro sincronizando item %s: %s", item_id, e, exc_info=True)
            entry.update({"status": JOB_ERROR, "error": str(e)})
            publish(PHASE_PROCESSING, "Falha ao sincronizar a conexão.", 20)

    # 3. Fechar o job.
    if failed == 0:
        status, phase = JOB_SUCCESS, PHASE_DONE
        message = f"Sync concluído: {totals['saved']} transações em {totals['accounts']} contas."
    elif succeeded == 0:
        status, phase = JOB_ERROR, PHASE_ERROR
        message = "Nenhuma conexão pôde ser sincronizada."
    else:
        status, phase = JOB_PARTIAL, PHASE_DONE
        message = (
            f"Sync parcial: {succeeded} de {total_items} conexões. "
            f"{totals['saved']} transações salvas."
        )

    final = update_job(
        job_id,
        status=status,
        phase=phase,
        progress=100,
        message=message,
        items_done=total_items,
        detail=detail,
        finished_at=datetime.now(timezone.utc),
        **totals,
    )

    # Dados novos no banco invalidam o cache do usuário (forecast, dashboard...).
    if totals["saved"]:
        try:
            from app.core.cache import invalidate_user_cache
            invalidate_user_cache(str(user_id))
        except Exception as e:
            logger.debug("[PluggySync] Falha ao invalidar cache de %s: %s", user_id, e)

    return final


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LONG-POLLING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def wait_for_job(
    job_id: str,
    user_id: str,
    cursor: int = 0,
    timeout: float = DEFAULT_LONG_POLL_TIMEOUT,
    db_poll_interval: float = DB_POLL_INTERVAL,
) -> Optional[dict]:
    """Devolve o estado do job assim que ele passar de `cursor`.

    Retorna o estado atual (com `changed=False`) se o timeout estourar, e
    None se o job não existir para este usuário.
    """
    timeout = max(0.0, min(timeout, MAX_LONG_POLL_TIMEOUT))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    # Assina ANTES da primeira leitura: um evento que chegue enquanto lemos
    # o banco fica retido no Event em vez de se perder.
    with events.AsyncSubscription(events.job_key(job_id)) as waiter:
        while True:
            state = await asyncio.to_thread(get_job_state, job_id, user_id)
            if state is None:
                return None
            if state["cursor"] > cursor or state["done"]:
                state["changed"] = state["cursor"] > cursor
                return state

            remaining = deadline - loop.time()
            if remaining <= 0:
                state["changed"] = False
                return state

            await waiter.wait(min(db_poll_interval, remaining))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STREAMING (SSE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_job(
    job_id: str,
    user_id: str,
    cursor: int = 0,
    heartbeat: float = SSE_HEARTBEAT_INTERVAL,
    max_duration: float = SSE_MAX_DURATION,
    db_poll_interval: float = DB_POLL_INTERVAL,
) -> AsyncIterator[str]:
    """Gera o corpo `text/event-stream` do job até ele terminar.

    Eventos: `state` a cada mudança, `ping` como heartbeat (mantém proxies
    de pé), `done` no fim e `error` se o job sumir. O cliente que cair
    reconecta mandando o último `cursor` — nada é perdido.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_duration
    last_cursor = cursor
    last_emit = loop.time()

    # `retry` instrui o EventSource nativo a reconectar em 3s.
    yield "retry: 3000\n\n"

    with events.AsyncSubscription(events.job_key(job_id)) as waiter:
        while True:
            state = await asyncio.to_thread(get_job_state, job_id, user_id)
            if state is None:
                yield _sse("error", {"job_id": job_id, "error": "Job não encontrado."})
                return

            if state["cursor"] > last_cursor:
                last_cursor = state["cursor"]
                last_emit = loop.time()
                yield _sse("state", state)

            if state["done"]:
                yield _sse("done", state)
                return

            remaining = deadline - loop.time()
            if remaining <= 0:
                # Sessão longa demais: fecha limpo e deixa o cliente reconectar.
                yield _sse("timeout", {"job_id": job_id, "cursor": last_cursor})
                return

            await waiter.wait(min(db_poll_interval, remaining))

            # Heartbeat por tempo, não por iteração: sem ele um proxy pode
            # derrubar a conexão durante os minutos em que o banco não responde.
            now = loop.time()
            if now - last_emit >= heartbeat:
                last_emit = now
                yield _sse("ping", {"cursor": last_cursor})
