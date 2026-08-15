from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class RejectedTransactionRecord(Base):
    """Dead Letter Queue da ingestão Open Finance.

    Toda transação que o firewall Pydantic recusa (valor nulo, data
    impossível, conta ausente...) para aqui em vez de sumir. Estava
    desenhada no docstring de RejectedTransaction desde o início e nunca
    tinha sido criada: as rejeições viviam só na memória do request, então
    um conector degradando em produção era invisível — o usuário via menos
    transações e ninguém ficava sabendo por quê.

    Serve a três coisas: reprocessar (o payload cru fica guardado),
    depurar (erro estruturado por campo) e alertar (taxa de rejeição por
    banco na janela recente, via `rejection_stats`).

    Nome com sufixo Record para não colidir com o schema Pydantic
    RejectedTransaction, que é o DTO da mesma coisa.
    """

    __tablename__ = "rejected_transactions"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True, index=True)
    item_id = Column(String, nullable=True)
    institution_id = Column(String, nullable=True)

    transaction_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)

    error_type = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    # JSON serializado (mesma convenção de pluggy_sync_jobs.detail):
    # {"amount": ["Field required"], "transaction_date": ["..."]}
    field_errors = Column(Text, nullable=True)

    # ATENÇÃO: pode conter PII (nome do pagador, documento em paymentData).
    # Nunca logar inteiro; expor só para o dono ou operação.
    raw_data = Column(Text, nullable=False)
    raw_data_truncated = Column(Boolean, nullable=False, default=False)

    batch_id = Column(String, nullable=True)
    rejected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_rejected_institution_date", "institution_id", "rejected_at"),
        Index("idx_rejected_user_date", "user_id", "rejected_at"),
    )
