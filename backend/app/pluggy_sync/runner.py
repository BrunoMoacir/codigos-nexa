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

import inspect
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.integrations.pluggy import PluggyClient
from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl import TransactionIngestor
from app.forecast.etl.bank_strategy.institutions import (
    DESCONHECIDO,
    extract_connector,
    resolve_institution_id,
)
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


# Paginação da Pluggy: pageSize padrão 20, máximo 500.
_PAGE_SIZE = 500
# Trava de segurança contra `totalPages` absurdo/loop infinito.
_MAX_PAGES = 200


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


def _supports_paging(pluggy) -> bool:
    """O cliente aceita os kwargs de paginação?

    Os dublês de teste (MockPluggyClient e afins) implementam a assinatura
    antiga `get_transactions(account_id)` e devolvem uma página só. Checar a
    assinatura evita tanto quebrá-los quanto mascarar um TypeError real
    vindo de dentro do cliente de verdade.
    """
    try:
        return "page" in inspect.signature(pluggy.get_transactions).parameters
    except (TypeError, ValueError):
        return False


def fetch_all_transactions(pluggy, account_id: str) -> list[dict]:
    """TODAS as transações da conta, percorrendo as páginas da Pluggy.

    Sem isto o sync ingeria só a primeira página — com o pageSize padrão de
    20, um usuário com um ano de extrato entrava no ETL com 20 lançamentos e
    todo o resto do produto (recorrências, burn rate, tarifas) via um mês
    truncado.
    """
    if not _supports_paging(pluggy):
        response = pluggy.get_transactions(account_id)
        return list(response.get("results") or []) if isinstance(response, dict) else []

    results: list[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        response = pluggy.get_transactions(account_id, page=page, page_size=_PAGE_SIZE)
        if not isinstance(response, dict):
            break

        batch = response.get("results") or []
        results.extend(batch)

        try:
            total_pages = int(response.get("totalPages") or 1)
        except (TypeError, ValueError):
            total_pages = 1

        if not batch or page >= total_pages:
            break
        page += 1
    else:
        logger.warning(
            "[PluggySync] conta %s parou em %d páginas (limite de segurança)",
            account_id, _MAX_PAGES,
        )

    return results


def _resolve_institution(pluggy: PluggyClient, item_id: str) -> str:
    """
    Slug do banco do item, via GET /items/{id}.

    Nunca levanta: se a consulta falhar, o sync segue com "unknown" e a
    DefaultStrategy — perder o tratamento por banco é ruim, perder o sync
    inteiro é pior.
    """
    try:
        item = pluggy.get_item(item_id)
    except Exception as e:
        logger.warning("[PluggySync] Não resolveu o conector do item %s: %s", item_id, e)
        return DESCONHECIDO

    nome, connector_id = extract_connector(item)
    institution_id = resolve_institution_id(nome, connector_id)

    logger.info(
        "[PluggySync] Item %s → conector=%r institution_id=%s",
        item_id, nome, institution_id,
    )
    return institution_id


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

    # Banco do item: é GET /items/{id} que traz o `connector` (o objeto
    # Account não traz). Sem isso o institution_id caía sempre em "unknown" e
    # a BankStrategy do banco nunca rodava em produção.
    institution_padrao = _resolve_institution(pluggy, item_id)

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
            raw_results = fetch_all_transactions(pluggy, account_id)
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

            # A conta às vezes carrega o próprio conector (payload antigo,
            # mock); quando carrega, ela manda — é mais específica que o item.
            nome_conta, id_conta = extract_connector(account)
            institution_id = resolve_institution_id(nome_conta, id_conta)
            if institution_id == DESCONHECIDO:
                institution_id = institution_padrao

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
