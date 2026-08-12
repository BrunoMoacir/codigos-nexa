"""
app/pluggy_sync/runner.py — Trabalho bruto de sincronização de um item Pluggy.

Duas responsabilidades, ambas bloqueantes (rodam na thread do job):

  1. `wait_item_ready` — espera o item sair de UPDATING. É o motivo de toda
     essa máquina existir: logo após o widget conectar, GET /accounts devolve
     lista vazia porque a instituição ainda está entregando os dados. Sem a
     espera, o sync "termina com sucesso" tendo salvo zero transações.

  2. `sync_item_transactions` — contas → transações → ETL → Postgres. É o
     mesmo corpo que vivia em app/api/v1/routes/pluggy.py, agora com um
     callback `on_progress` para alimentar o long-polling/SSE.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.integrations.pluggy import PluggyClient
from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl import TransactionIngestor
from app.forecast.etl.runner import run_etl_pipeline
from app.pluggy_sync import events

logger = logging.getLogger(__name__)

# Estados terminais do item na Pluggy.
ITEM_READY = frozenset({"UPDATED"})
ITEM_BLOCKED = {
    "LOGIN_ERROR": "Credenciais inválidas ou expiradas — reconecte a conta.",
    "WAITING_USER_INPUT": "O banco pediu autenticação (MFA). Conclua no widget da Pluggy.",
    "ERROR": "A Pluggy não conseguiu atualizar esta conexão.",
    "OUTDATED": "A conexão está desatualizada — reconecte a conta.",
}

# Quanto esperar entre reconsultas quando o webhook não chega (fallback).
_DEFAULT_POLL_INTERVAL = 5.0

ProgressFn = Callable[..., None]


class ItemNotReady(Exception):
    """Item não ficou pronto: expirou o tempo ou a Pluggy devolveu erro."""

    def __init__(self, status_str: str, message: str) -> None:
        super().__init__(message)
        self.item_status = status_str
        self.message = message


def get_item_status(pluggy: PluggyClient, item_id: str) -> Optional[str]:
    """Status atual do item, ou None se a consulta falhar."""
    try:
        item = pluggy.get_item(item_id)
    except Exception as e:
        logger.warning("[PluggySync] Falha ao consultar item %s: %s", item_id, e)
        return None
    if not isinstance(item, dict):
        return None
    return str(item.get("status") or "").upper() or None


def wait_item_ready(
    pluggy: PluggyClient,
    item_id: str,
    timeout: float,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    on_progress: Optional[ProgressFn] = None,
) -> str:
    """Bloqueia até o item ficar UPDATED (ou levanta ItemNotReady).

    Acorda imediatamente quando o webhook da Pluggy publica `item:{item_id}`;
    o `poll_interval` é só a rede de segurança para o caso do webhook não
    estar configurado ou o evento cair em outro worker.
    """
    deadline = time.monotonic() + timeout

    with events.ThreadSubscription(events.item_key(item_id)) as waiter:
        while True:
            status_str = get_item_status(pluggy, item_id)

            if status_str is None:
                # Sem resposta da Pluggy: segue esperando até o deadline —
                # instabilidade momentânea não deve abortar o sync.
                pass
            elif status_str in ITEM_READY:
                return status_str
            elif status_str in ITEM_BLOCKED:
                raise ItemNotReady(status_str, ITEM_BLOCKED[status_str])

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ItemNotReady(
                    status_str or "UNKNOWN",
                    "O banco não devolveu os dados a tempo. "
                    "A sincronização continua em segundo plano — tente de novo em alguns minutos.",
                )

            if on_progress is not None:
                on_progress(item_status=status_str, remaining=max(remaining, 0.0))

            waiter.wait(min(poll_interval, remaining))


def sync_item_transactions(
    db: Session,
    user_id: str,
    item_id: str,
    on_progress: Optional[ProgressFn] = None,
) -> dict:
    """Sincroniza contas/transações de um item Pluggy para transactions_clean."""
    pluggy = PluggyClient()

    accounts_resp = pluggy.get_accounts(item_id)
    accounts = accounts_resp.get("results", []) if isinstance(accounts_resp, dict) else []

    # Snapshot de saldo real por conta (poupança, corrente, ...) — base da
    # personalização do OPP. Falha silenciosamente; nunca derruba o sync.
    from app.core.db.balances import save_account_balances
    balances_saved = save_account_balances(str(user_id), item_id, accounts)

    total_accounts = 0
    total_received = 0
    total_valid = 0
    total_saved = 0
    errors: list[str] = []

    for index, account in enumerate(accounts):
        account_id = account.get("id")
        if not account_id:
            continue

        total_accounts += 1
        if on_progress is not None:
            on_progress(
                account_index=index + 1,
                accounts_total=len(accounts),
                account_id=account_id,
            )

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
                user_id=str(user_id),
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
        "balances_saved": balances_saved,
        "errors": errors,
    }
