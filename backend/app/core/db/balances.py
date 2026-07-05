"""
app/core/db/balances.py — persistência e leitura de saldos reais (Pluggy).

Gravação: save_account_balances() é chamado no sync de item
(app/api/v1/routes/pluggy.py) com o payload cru de get_accounts().
Append-only — cada sync gera um snapshot novo por conta; leitores usam
sempre o mais recente. Falha silenciosamente (warning): persistir saldo
nunca pode derrubar o sync de transações.

Leitura: get_latest_balance() / get_latest_balances_by_bank() alimentam a
personalização do OPP (poupança vs. CDI com saldo real, Bank Match).

Staleness: saldo com mais de _MAX_AGE_DAYS não é retornado — melhor cair
no modo genérico do que afirmar um saldo que o usuário pode não ter mais.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_AGE_DAYS = 7

# Mapeamento dos tipos/subtipos do Pluggy para o tipo interno.
# Pluggy usa type=BANK/CREDIT + subtype=CHECKING_ACCOUNT/SAVINGS_ACCOUNT/
# CREDIT_CARD; o mock e payloads antigos usam type=CHECKING direto.
def normalize_account_type(account: dict) -> str:
    raw = f"{account.get('type', '')} {account.get('subtype', '')}".upper()
    if "SAVINGS" in raw or "POUPANCA" in raw or "POUPANÇA" in raw:
        return "SAVINGS"
    if "CHECKING" in raw or "CORRENTE" in raw:
        return "CHECKING"
    if "CREDIT" in raw:
        return "CREDIT"
    if "INVESTMENT" in raw:
        return "INVESTMENT"
    return "OTHER"


def _extract_bank_name(account: dict) -> Optional[str]:
    connector = account.get("connector")
    if isinstance(connector, dict) and connector.get("name"):
        return str(connector["name"])
    for key in ("institutionName", "marketingName", "name"):
        value = account.get(key)
        if value:
            return str(value)
    return None


@dataclass
class BalanceSnapshot:
    balance: float
    bank_name: Optional[str]
    account_type: str
    captured_at: datetime


def save_account_balances(user_id: str, item_id: str | None, accounts: list[dict]) -> int:
    """Persiste um snapshot de saldo por conta. Retorna quantos gravou."""
    if not accounts:
        return 0
    saved = 0
    try:
        from app.core.database import SessionLocal
        from app.core.models.account_balance import AccountBalance

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for account in accounts:
                account_id = account.get("id")
                balance = account.get("balance")
                if not account_id or balance is None:
                    continue
                try:
                    balance = float(balance)
                except (TypeError, ValueError):
                    continue
                db.add(AccountBalance(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    item_id=item_id,
                    account_id=str(account_id),
                    bank_name=_extract_bank_name(account),
                    account_type=normalize_account_type(account),
                    balance=balance,
                    currency=str(account.get("currencyCode") or "BRL"),
                    captured_at=now,
                ))
                saved += 1
            db.commit()
    except Exception as exc:
        logger.warning("[balances] save user=%s item=%s: %s", user_id, item_id, exc)
        return 0
    return saved


def get_latest_balance(
    user_id: str,
    account_type: str,
    max_age_days: int = _MAX_AGE_DAYS,
) -> Optional[BalanceSnapshot]:
    """Saldo mais recente do tipo, somado entre contas do mesmo tipo quando o
    usuário tem mais de uma (ex: poupança em dois bancos). None quando não há
    snapshot dentro da janela de frescor."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT ab.balance, ab.bank_name, ab.captured_at"
                    " FROM account_balances ab"
                    " JOIN ("
                    "   SELECT account_id, MAX(captured_at) AS max_at"
                    "   FROM account_balances"
                    "   WHERE user_id = :uid AND account_type = :atype AND captured_at >= :cutoff"
                    "   GROUP BY account_id"
                    " ) latest ON latest.account_id = ab.account_id AND latest.max_at = ab.captured_at"
                    " WHERE ab.user_id = :uid AND ab.account_type = :atype"
                ),
                {"uid": user_id, "atype": account_type, "cutoff": cutoff},
            ).fetchall()
        if not rows:
            return None
        total = sum(float(r[0]) for r in rows)
        newest = max(r[2] for r in rows)
        banks = {r[1] for r in rows if r[1]}
        return BalanceSnapshot(
            balance=round(total, 2),
            bank_name=next(iter(banks)) if len(banks) == 1 else None,
            account_type=account_type,
            captured_at=newest,
        )
    except Exception as exc:
        logger.warning("[balances] get_latest user=%s type=%s: %s", user_id, account_type, exc)
        return None


def get_latest_balances_by_bank(
    user_id: str,
    max_age_days: int = _MAX_AGE_DAYS,
) -> dict[str, float]:
    """{bank_name: saldo total} mais recente por banco (todas as contas não-crédito)."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT ab.bank_name, ab.balance"
                    " FROM account_balances ab"
                    " JOIN ("
                    "   SELECT account_id, MAX(captured_at) AS max_at"
                    "   FROM account_balances"
                    "   WHERE user_id = :uid AND captured_at >= :cutoff"
                    "   GROUP BY account_id"
                    " ) latest ON latest.account_id = ab.account_id AND latest.max_at = ab.captured_at"
                    " WHERE ab.user_id = :uid AND ab.account_type != 'CREDIT'"
                    "   AND ab.bank_name IS NOT NULL"
                ),
                {"uid": user_id, "cutoff": cutoff},
            ).fetchall()
        result: dict[str, float] = {}
        for bank, balance in rows:
            result[bank] = round(result.get(bank, 0.0) + float(balance), 2)
        return result
    except Exception as exc:
        logger.warning("[balances] by_bank user=%s: %s", user_id, exc)
        return {}


__all__ = [
    "BalanceSnapshot",
    "save_account_balances",
    "get_latest_balance",
    "get_latest_balances_by_bank",
    "normalize_account_type",
]
