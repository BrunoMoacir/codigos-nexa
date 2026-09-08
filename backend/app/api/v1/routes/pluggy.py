# app/api/v1/routes/pluggy.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, List, Optional
import asyncio
import logging
import requests as http_requests
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.integrations.pluggy import PluggyClient
from app.core.security import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.models.pluggy_item import PluggyItem
from app.core.webhook_security import resolve_user_from_item, verify_webhook_token
from app.pluggy_sync import events as sync_events
from app.pluggy_sync import service as sync_service
from app.pluggy_sync.runner import sync_item_transactions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pluggy", "Open Finance"])


def _sync_item_transactions(
    db: Session,
    current_user_str: str,
    item_id: str,
) -> dict:
    """Compat: o corpo do sync agora vive em app/pluggy_sync/runner.py."""
    return sync_item_transactions(db=db, user_id=str(current_user_str), item_id=item_id)


class ConnectTokenResponse(BaseModel):
    connect_token: str

class SaveItemRequest(BaseModel):
    item_id: str
    connector_name: Optional[str] = None

class CardResponse(BaseModel):
    account_id: str
    bank_name: Optional[str] = None
    brand: Optional[str] = None
    level: Optional[str] = None
    last4: Optional[str] = None
    credit_limit: Optional[float] = None
    available_credit_limit: Optional[float] = None
    balance_close_date: Optional[str] = None
    balance_due_date: Optional[str] = None
    currency: str = "BRL"
    captured_at: str

class ManualCardRequest(BaseModel):
    bank_name: str
    brand: Optional[str] = None
    level: Optional[str] = None
    last4: Optional[str] = None
    credit_limit: Optional[float] = None
    available_credit_limit: Optional[float] = None

@router.post("/connect-token", response_model=ConnectTokenResponse, summary="Gera um Connect Token para o Widget")
def create_connect_token(current_user_str: str = Depends(get_current_user)):
    """Gera um connect_token obrigatório para inicializar o Widget Pluggy no Frontend."""
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    try:
        user_identifier = str(current_user_str)
        logger.info("Gerando connect-token para banco do usuário %s", user_identifier)
        
        pluggy = PluggyClient()
        connect_token = pluggy.create_connect_token(clientUserId=user_identifier)
        
        token_str = ""
        if isinstance(connect_token, dict):
            token_str = connect_token.get("accessToken", connect_token.get("connectToken", ""))
        elif hasattr(connect_token, "accessToken"):
            token_str = connect_token.accessToken
        else:
            token_str = str(connect_token)

        if not token_str:
            raise Exception("Token inválido retornado pelo SDK da Pluggy")

        return ConnectTokenResponse(connect_token=token_str)
        
    except Exception as e:
        logger.error("Erro ao gerar connect token Pluggy: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar token de conexão. Tente novamente em alguns instantes.",
        )


@router.get("/items", summary="Lista os Items (contas bancárias) conectados do usuário")
def list_user_items(
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna os items conectados do usuário.

    Observação: a Pluggy vem retornando 401 no GET /items (listagem) em alguns tenants,
    mas GET /items/{id} funciona. Mantemos dados reais persistindo os item_ids no DB.
    """
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    try:
        pluggy = PluggyClient()

        # Tentativa 1: listagem nativa da Pluggy (se estiver liberada)
        resp = http_requests.get(
            f"{settings.PLUGGY_BASE_URL}/items",
            params={"clientUserId": str(current_user_str)},
            headers=pluggy._headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()

        # Tentativa 2 (fallback real): buscar item_ids persistidos e resolver via /items/{id}
        if resp.status_code == 401:
            rows = (
                db.query(PluggyItem)
                .filter(PluggyItem.user_id == str(current_user_str))
                .all()
            )
            results = []
            for row in rows:
                r = http_requests.get(
                    f"{settings.PLUGGY_BASE_URL}/items/{row.item_id}",
                    headers=pluggy._headers(),
                    timeout=15,
                )
                if r.status_code == 200:
                    results.append(r.json())
                else:
                    logger.warning(
                        "Pluggy /items/%s returned %s: %s",
                        row.item_id,
                        r.status_code,
                        r.text,
                    )
            return {"results": results, "total": len(results)}

        logger.warning("Pluggy /items returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro ao consultar contas bancárias. Tente novamente em alguns instantes.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao listar items Pluggy: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar contas bancárias. Tente novamente em alguns instantes.",
        )

@router.post("/items", summary="Salva um Item conectado pelo Widget")
def save_user_item(
    request: SaveItemRequest,
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quando o Widget do frontend conecta uma conta com sucesso, salva o item_id."""
    try:
        existing = db.query(PluggyItem).filter(
            PluggyItem.user_id == str(current_user_str),
            PluggyItem.item_id == request.item_id
        ).first()

        if not existing:
            record = PluggyItem(
                id=str(uuid.uuid4()),
                user_id=str(current_user_str),
                item_id=request.item_id,
                connector_name=request.connector_name,
            )
            db.add(record)
            db.commit()

        return {"success": True, "message": "Item salvo com sucesso"}
    except Exception as e:
        db.rollback()
        logger.error("Erro ao salvar item do widget: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao salvar conta bancária. Tente novamente.",
        )


@router.post("/sandbox", summary="Cria um Item de Sandbox para testes")
def create_sandbox_item(
    perf_multiplier: int = 1,
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria uma conexão fake (Sandbox) com a Pluggy Bank para testes de desenvolvimento."""
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    try:
        pluggy = PluggyClient()
        result = pluggy.create_sandbox_item(
            clientUserId=str(current_user_str),
            perf_multiplier=perf_multiplier,
        )

        item_id = None
        connector_name = None
        if isinstance(result, dict):
            item_id = result.get("id")
            connector = result.get("connector") or {}
            connector_name = connector.get("name") if isinstance(connector, dict) else None

        if item_id:
            record = PluggyItem(
                id=str(uuid.uuid4()),
                user_id=str(current_user_str),
                item_id=str(item_id),
                connector_name=connector_name,
            )
            try:
                db.add(record)
                db.commit()
            except Exception:
                db.rollback()

        sync_report = None
        if item_id:
            try:
                sync_report = _sync_item_transactions(
                    db=db,
                    current_user_str=str(current_user_str),
                    item_id=str(item_id),
                )
            except Exception as e:
                logger.warning("Sandbox created, but sync failed for item %s: %s", item_id, e)

        return {"success": True, "item": result, "sync": sync_report}
    except Exception as e:
        logger.error("Erro ao criar sandbox item Pluggy: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar item de sandbox. Verifique as credenciais Pluggy.",
        )


@router.post("/sync", summary="Sincroniza transações reais da Pluggy (modo bloqueante — legado)")
def sync_user_items_transactions(
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sincroniza tudo dentro do request e só responde no fim.

    Só funciona quando os items já estão UPDATED (ex.: sandbox). Para uma
    conexão recém-criada, o banco ainda está entregando os dados e este
    endpoint devolve zero transações — ou estoura o timeout do proxy antes
    de responder. Use `POST /pluggy/sync/jobs` + long-polling/SSE.
    """
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    rows = (
        db.query(PluggyItem)
        .filter(PluggyItem.user_id == str(current_user_str))
        .all()
    )
    if not rows:
        return {
            "success": True,
            "message": "Nenhum item Pluggy encontrado para o usuário.",
            "items": [],
            "totals": {"items": 0, "accounts": 0, "received": 0, "valid": 0, "saved": 0},
        }

    reports = []
    totals = {"items": 0, "accounts": 0, "received": 0, "valid": 0, "saved": 0}
    for row in rows:
        report = _sync_item_transactions(
            db=db,
            current_user_str=str(current_user_str),
            item_id=row.item_id,
        )
        reports.append(report)
        totals["items"] += 1
        totals["accounts"] += report.get("accounts", 0)
        totals["received"] += report.get("received", 0)
        totals["valid"] += report.get("valid", 0)
        totals["saved"] += report.get("saved", 0)

    return {"success": True, "items": reports, "totals": totals}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC ASSÍNCRONO — job + long-polling + streaming (SSE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# A Pluggy entrega os dados quando o banco responde — de segundos a
# minutos, com MFA no meio. O cliente cria um job e acompanha por um dos
# dois canais; ambos partilham o mesmo cursor (`version` do job), então dá
# para alternar entre eles ou reconectar sem perder evento.
#
#   POST /pluggy/sync/jobs                  → 202 {job_id, cursor, ...}
#   GET  /pluggy/sync/jobs/{id}?cursor=N    → pendura até mudar (long-poll)
#   GET  /pluggy/sync/jobs/{id}/stream      → text/event-stream (SSE)

@router.post(
    "/sync/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Inicia uma sincronização assíncrona (long-polling/SSE)",
)
def start_sync_job(
    force: bool = Query(
        default=False,
        description="Cria um job novo mesmo se já houver um em andamento.",
    ),
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enfileira o sync e devolve na hora o job para acompanhamento.

    Se já houver um job em andamento do mesmo usuário, devolve esse mesmo
    job (`reused: true`) em vez de duplicar o trabalho — dois cliques no
    botão sincronizar não viram duas ETLs concorrentes.
    """
    if not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
        )

    user_id = str(current_user_str)

    if not force:
        active = sync_service.find_active_job(db, user_id)
        if active is not None:
            state = sync_service.job_to_dict(active)
            state["reused"] = True
            return state

    item_ids = sync_service.user_item_ids(db, user_id)
    job = sync_service.create_job(db, user_id, item_ids)
    sync_service.start_job(job.id, user_id)

    state = sync_service.job_to_dict(job)
    state["reused"] = False
    return state


@router.get("/sync/jobs", summary="Lista os últimos jobs de sincronização do usuário")
def list_sync_jobs(
    limit: int = Query(default=10, ge=1, le=50),
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = sync_service.list_jobs(db, str(current_user_str), limit=limit)
    return {"jobs": [sync_service.job_to_dict(j) for j in jobs]}


@router.get("/sync/jobs/{job_id}", summary="Long-polling do estado de um job de sync")
async def poll_sync_job(
    job_id: str,
    cursor: int = Query(
        default=0,
        ge=0,
        description="Último `cursor` recebido. A resposta só volta quando o job passar dele.",
    ),
    timeout: float = Query(
        default=sync_service.DEFAULT_LONG_POLL_TIMEOUT,
        ge=0,
        le=sync_service.MAX_LONG_POLL_TIMEOUT,
        description="Segundos que a conexão pode ficar pendurada (máx. 30).",
    ),
    current_user_str: str = Depends(get_current_user),
):
    """Segura a resposta até o job avançar, terminar ou estourar o timeout.

    Timeout não é erro: devolve o estado atual com `changed: false` e o
    cliente reabre a conexão com o mesmo cursor. Job já terminado responde
    imediatamente, mesmo sem mudança de cursor.
    """
    state = await sync_service.wait_for_job(
        job_id=job_id,
        user_id=str(current_user_str),
        cursor=cursor,
        timeout=timeout,
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job de sincronização não encontrado.",
        )
    return state


@router.get("/sync/jobs/{job_id}/stream", summary="Streaming (SSE) do progresso de um job")
async def stream_sync_job(
    job_id: str,
    cursor: int = Query(default=0, ge=0, description="Último `cursor` recebido (retomada)."),
    current_user_str: str = Depends(get_current_user),
):
    """Envia o progresso como `text/event-stream` até o job terminar.

    Eventos: `state` (mudou algo), `ping` (heartbeat 15s), `done` (fim) e
    `timeout` (sessão longa demais — reconecte com o último cursor).

    O EventSource nativo do navegador não manda header Authorization: o
    frontend consome com `fetch` + ReadableStream. Token em query string
    ficaria gravado nos logs de acesso, então não é aceito aqui.
    """
    # Sem Depends(get_db) aqui de propósito: a dependência com yield só é
    # fechada quando o corpo termina de ser enviado, e um SSE fica aberto por
    # minutos — seria uma conexão do pool presa por cliente conectado.
    user_id = str(current_user_str)
    if await asyncio.to_thread(sync_service.get_job_state, job_id, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job de sincronização não encontrado.",
        )

    return StreamingResponse(
        sync_service.stream_job(job_id=job_id, user_id=user_id, cursor=cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Desliga o buffering de proxies (nginx/Railway): sem isso os
            # eventos só chegariam ao cliente quando o buffer enchesse.
            "X-Accel-Buffering": "no",
        },
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK DE ITEMS — é o que torna o long-poll/SSE instantâneo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Eventos que significam "o banco entregou os dados".
_ITEM_READY_EVENTS = {
    "item/updated",
    "item/login_succeeded",
    "transactions/created",
    "transactions/updated",
}


@router.get("/cards", response_model=List[CardResponse], summary="Lista os cartões de crédito do usuário")
def list_user_cards(current_user_str: str = Depends(get_current_user)):
    """Cartões (bandeira, limite, vencimento) capturados no último sync de cada conta CREDIT.

    Vazio até o usuário conectar um banco e o sync persistir pelo menos uma
    conta do tipo CREDIT — ver app/core/db/cards.py.
    """
    from app.core.db.cards import get_cards

    cards = get_cards(str(current_user_str))
    return [
        CardResponse(
            account_id=c.account_id,
            bank_name=c.bank_name,
            brand=c.brand,
            level=c.level,
            last4=c.last4,
            credit_limit=c.credit_limit,
            available_credit_limit=c.available_credit_limit,
            balance_close_date=c.balance_close_date,
            balance_due_date=c.balance_due_date,
            currency=c.currency,
            captured_at=str(c.captured_at),
        )
        for c in cards
    ]


@router.post("/cards/manual", response_model=CardResponse, summary="Cadastra um cartão manualmente")
def add_manual_card(payload: ManualCardRequest, current_user_str: str = Depends(get_current_user)):
    """Para bancos/cartões que o Open Finance ainda não cobre — o usuário informa os dados na mão."""
    from app.core.db.cards import get_cards, save_manual_card

    account_id = save_manual_card(
        user_id=str(current_user_str),
        bank_name=payload.bank_name,
        brand=payload.brand,
        level=payload.level,
        last4=payload.last4,
        credit_limit=payload.credit_limit,
        available_credit_limit=payload.available_credit_limit,
    )
    created = next((c for c in get_cards(str(current_user_str)) if c.account_id == account_id), None)
    if not created:
        raise HTTPException(status_code=500, detail="Falha ao salvar cartão")
    return CardResponse(
        account_id=created.account_id,
        bank_name=created.bank_name,
        brand=created.brand,
        level=created.level,
        last4=created.last4,
        credit_limit=created.credit_limit,
        available_credit_limit=created.available_credit_limit,
        balance_close_date=created.balance_close_date,
        balance_due_date=created.balance_due_date,
        currency=created.currency,
        captured_at=str(created.captured_at),
    )


@router.post("/webhook", status_code=status.HTTP_200_OK, summary="Webhook de eventos de item da Pluggy")
def receive_item_webhook(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """Recebe `item/*` da Pluggy e acorda quem está esperando.

    Sem isto, o job só descobriria que o item ficou pronto no próximo tick
    do poller (5s) — com isto, no instante em que a Pluggy avisa. E se
    ninguém estiver esperando (usuário fechou o app), dispara o sync
    sozinho, para os dados já estarem lá quando ele voltar.

    Mesma postura de segurança do /transactions/webhook: segredo
    compartilhado obrigatório e dono resolvido server-side por item_id.
    """
    verify_webhook_token(request)

    event = str(payload.get("event") or payload.get("eventType") or "").lower()
    item_id = str(
        payload.get("itemId")
        or (payload.get("item") or {}).get("id")
        or payload.get("id")
        or ""
    )

    if not item_id:
        return {"received": True, "ignored": True, "reason": "payload sem itemId"}

    # Acorda o job que estiver esperando este item (mesmo worker).
    sync_events.publish(sync_events.item_key(item_id))

    user_id = resolve_user_from_item(item_id)
    if user_id is None:
        # Item de outro ambiente/cliente: nada a fazer. 200 (e não 404) para
        # não colocar a Pluggy num loop de retentativa.
        logger.info("[PluggyWebhook] item_id=%s sem dono conhecido — ignorado", item_id)
        return {"received": True, "ignored": True, "reason": "item desconhecido"}

    if event not in _ITEM_READY_EVENTS:
        return {"received": True, "event": event, "item_id": item_id, "started_job": False}

    # Job em andamento já vai capturar o evento no seu próprio loop.
    active = sync_service.find_active_job(db, user_id)
    if active is not None:
        return {
            "received": True,
            "event": event,
            "item_id": item_id,
            "started_job": False,
            "job_id": active.id,
        }

    if not settings.PLUGGY_AUTOSYNC_ON_WEBHOOK:
        return {"received": True, "event": event, "item_id": item_id, "started_job": False}

    job = sync_service.create_job(db, user_id, [item_id])
    sync_service.start_job(job.id, user_id)
    logger.info("[PluggyWebhook] %s em %s → job %s iniciado", event, item_id, job.id)

    return {
        "received": True,
        "event": event,
        "item_id": item_id,
        "started_job": True,
        "job_id": job.id,
    }
