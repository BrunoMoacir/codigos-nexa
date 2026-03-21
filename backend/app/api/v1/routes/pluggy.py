# app/api/v1/routes/pluggy.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import logging
import requests as http_requests
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.open_finance.pluggy import PluggyClient
from app.core.security import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.pluggy_item import PluggyItem
from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor
from app.etl.runner import run_etl_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pluggy", "Open Finance"])


def _sync_item_transactions(
    db: Session,
    current_user_str: str,
    item_id: str,
) -> dict:
    """Sincroniza contas/transações de um item Pluggy para transactions_clean."""
    pluggy = PluggyClient()

    accounts_resp = pluggy.get_accounts(item_id)
    accounts = accounts_resp.get("results", []) if isinstance(accounts_resp, dict) else []

    total_accounts = 0
    total_received = 0
    total_valid = 0
    total_saved = 0
    errors: list[str] = []

    for account in accounts:
        account_id = account.get("id")
        if not account_id:
            continue

        total_accounts += 1
        try:
            raw_transactions = pluggy.get_transactions(account_id)
            raw_results = raw_transactions.get("results", []) if isinstance(raw_transactions, dict) else []
            total_received += len(raw_results)

            if not raw_results:
                continue

            # Ajustes de compatibilidade do payload Pluggy -> schema local
            normalized_results = []
            for tx in raw_results:
                if not isinstance(tx, dict):
                    continue
                tx_n = dict(tx)
                merchant = tx_n.get("merchant")
                if isinstance(merchant, dict):
                    tx_n["merchant"] = merchant.get("businessName") or merchant.get("name")
                if not tx_n.get("description") and tx_n.get("descriptionRaw"):
                    tx_n["description"] = tx_n.get("descriptionRaw")
                normalized_results.append(tx_n)

            connector = account.get("connector") if isinstance(account.get("connector"), dict) else {}
            connector_id = str(
                connector.get("id")
                or account.get("connectorId")
                or "unknown"
            )
            institution_map = {
                "201": "nubank",
                "202": "itau",
                "203": "bradesco",
                "204": "inter",
                "0": "pluggy_sandbox",
            }
            institution_id = institution_map.get(connector_id, "unknown")

            batch_result = TransactionBatchResult.from_raw_batch(
                raw_data=normalized_results,
                institution_id=institution_id,
                item_id=item_id,
                fetched_at=datetime.now(timezone.utc),
            )
            total_valid += batch_result.total_valid

            if not batch_result.valid_transactions:
                continue

            ingestor = TransactionIngestor()
            clean_df, _ = ingestor.process(batch_result.valid_transactions)
            processed_df = run_etl_pipeline(
                db=db,
                transactions_df=clean_df,
                user_id=str(current_user_str),
                account_id=account_id,
            )
            total_saved += len(processed_df) if processed_df is not None else 0
        except Exception as e:
            errors.append(f"account {account_id}: {e}")

    return {
        "item_id": item_id,
        "accounts": total_accounts,
        "received": total_received,
        "valid": total_valid,
        "saved": total_saved,
        "errors": errors,
    }

class ConnectTokenResponse(BaseModel):
    connect_token: str

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
        logger.info(f"Gerando connect-token para banco do usuário {user_identifier}")
        
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
        logger.error(f"Erro ao gerar connect token Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}"
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
            detail=f"Pluggy /items falhou ({resp.status_code}). {resp.text}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar items Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao comunicar com a Pluggy: {str(e)}",
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
        logger.error(f"Erro ao criar sandbox item Pluggy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar sandbox: {str(e)}",
        )


@router.post("/sync", summary="Sincroniza transações reais da Pluggy para o usuário logado")
def sync_user_items_transactions(
    current_user_str: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
