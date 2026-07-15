from sqlalchemy import Column, DateTime, Float, Index, String
from sqlalchemy.sql import func

from app.core.database import Base


class AccountBalance(Base):
    """Snapshot de saldo real de conta vindo do Pluggy (append-only).

    Persistido a cada sync de item (app/api/v1/routes/pluggy.py) — antes
    disso o `balance` retornado por get_accounts() era descartado, o que
    impedia personalizar o OPP com saldo real (poupança, conta corrente).
    Ver docs/OPP4_POUPANCA_CDI_PLANO.md (OPP4-D/E) e docs/OPP.md §3.2.
    """

    __tablename__ = "account_balances"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=True)
    account_id = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    account_type = Column(String, nullable=False)  # CHECKING | SAVINGS | CREDIT | INVESTMENT | OTHER
    balance = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="BRL")
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_account_balances_user_type", "user_id", "account_type", "captured_at"),
    )
