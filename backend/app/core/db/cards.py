"""
app/core/db/cards.py — persistência e leitura de dados de cartão de crédito (Pluggy).

Gravação: save_credit_cards() é chamado no sync de item (app/pluggy_sync/runner.py),
logo após save_account_balances() — mesmo payload cru de get_accounts(), mesmo
padrão append-only, mesma tolerância a falha (nunca derruba o sync de transações).

Leitura: get_cards() devolve o snapshot mais recente por conta CREDIT do usuário,
usado pela seção "Cartões" do app.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.core.db.balances import _extract_bank_name, normalize_account_type

logger = logging.getLogger(__name__)


def _to_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class CardSnapshot:
    account_id: str
    bank_name: Optional[str]
    brand: Optional[str]
    level: Optional[str]
    last4: Optional[str]
    credit_limit: Optional[float]
    available_credit_limit: Optional[float]
    balance_close_date: Optional[str]
    balance_due_date: Optional[str]
    currency: str
    captured_at: datetime


def save_credit_cards(user_id: str, item_id: str | None, accounts: list[dict]) -> int:
    """Persiste um snapshot de cartão por conta CREDIT. Retorna quantos gravou."""
    credit_accounts = [a for a in accounts if normalize_account_type(a) == "CREDIT"]
    if not credit_accounts:
        return 0
    saved = 0
    try:
        from app.core.database import SessionLocal
        from app.core.models.credit_card import CreditCard

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for account in credit_accounts:
                account_id = account.get("id")
                if not account_id:
                    continue
                credit_data = account.get("creditData") or {}
                number = account.get("number") or credit_data.get("cardNumber") or ""
                last4 = str(number)[-4:] if number else None
                db.add(CreditCard(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    item_id=item_id,
                    account_id=str(account_id),
                    bank_name=_extract_bank_name(account),
                    brand=credit_data.get("brand"),
                    level=credit_data.get("level"),
                    last4=last4,
                    credit_limit=_to_float(credit_data.get("creditLimit")),
                    available_credit_limit=_to_float(credit_data.get("availableCreditLimit")),
                    balance_close_date=credit_data.get("balanceCloseDate"),
                    balance_due_date=credit_data.get("balanceDueDate"),
                    currency=str(account.get("currencyCode") or "BRL"),
                    captured_at=now,
                ))
                saved += 1
            db.commit()
    except Exception as exc:
        logger.warning("[cards] save user=%s item=%s: %s", user_id, item_id, exc)
        return 0
    return saved


def get_cards(user_id: str) -> list[CardSnapshot]:
    """Cartões do usuário — snapshot mais recente por conta CREDIT."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT cc.account_id, cc.bank_name, cc.brand, cc.level, cc.last4,"
                    "       cc.credit_limit, cc.available_credit_limit,"
                    "       cc.balance_close_date, cc.balance_due_date, cc.currency, cc.captured_at"
                    " FROM credit_cards cc"
                    " JOIN ("
                    "   SELECT account_id, MAX(captured_at) AS max_at"
                    "   FROM credit_cards WHERE user_id = :uid GROUP BY account_id"
                    " ) latest ON latest.account_id = cc.account_id AND latest.max_at = cc.captured_at"
                    " WHERE cc.user_id = :uid"
                    " ORDER BY cc.captured_at DESC"
                ),
                {"uid": user_id},
            ).fetchall()
        return [
            CardSnapshot(
                account_id=r[0], bank_name=r[1], brand=r[2], level=r[3], last4=r[4],
                credit_limit=r[5], available_credit_limit=r[6],
                balance_close_date=r[7], balance_due_date=r[8], currency=r[9], captured_at=r[10],
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning("[cards] get user=%s: %s", user_id, exc)
        return []


__all__ = ["CardSnapshot", "save_credit_cards", "get_cards"]
