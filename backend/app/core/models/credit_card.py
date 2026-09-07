from sqlalchemy import Column, DateTime, Float, Index, String
from sqlalchemy.sql import func

from app.core.database import Base


class CreditCard(Base):
    """Snapshot de dados de cartão de crédito vindos do Pluggy (append-only).

    Espelha o padrão de AccountBalance (app/core/models/account_balance.py):
    cada sync grava um snapshot novo por conta CREDIT; leitores usam sempre
    o mais recente. `creditData` do Pluggy era buscado em get_accounts() e
    descartado — isso persiste bandeira/nível/limite/vencimento reais.
    """

    __tablename__ = "credit_cards"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=True)
    account_id = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    brand = Column(String, nullable=True)                        # VISA, MASTERCARD, ELO...
    level = Column(String, nullable=True)                          # GOLD, PLATINUM, BLACK...
    last4 = Column(String, nullable=True)                           # últimos 4 dígitos, quando a Pluggy expõe
    credit_limit = Column(Float, nullable=True)
    available_credit_limit = Column(Float, nullable=True)
    balance_close_date = Column(String, nullable=True)              # data de fechamento da fatura (ISO)
    balance_due_date = Column(String, nullable=True)                # data de vencimento da fatura (ISO)
    currency = Column(String, nullable=False, default="BRL")
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_credit_cards_user", "user_id", "captured_at"),
    )
