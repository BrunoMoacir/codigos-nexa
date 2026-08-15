from sqlalchemy import Boolean, Column, DateTime, Float, Index, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ShadowInvoice(Base):
    """Obrigação futura detectada a partir do histórico (assinatura ou parcela).

    "Shadow" porque o banco não conta que ela existe: é o Nexa que deduz,
    do padrão do extrato, que R$ 49,90 de Netflix e a parcela 5/10 do
    notebook vão cair no mês que vem. É a base do safe-to-spend honesto —
    saldo menos o que já está comprometido.

    O Step 5 do ETL detectava e jogava fora (`# TODO: Salvar shadow invoices`),
    então cada consulta reprocessava o histórico inteiro para redescobrir o
    mesmo, e nada conseguia comparar o previsto com o que de fato veio.

    Idempotente por (user_id, merchant_key, type): re-sync atualiza a linha
    existente em vez de empilhar duplicata — o detector roda a cada
    sincronização sobre a mesma série.
    """

    __tablename__ = "shadow_invoices"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True)

    # SUBSCRIPTION | INSTALLMENT
    type = Column(String(20), nullable=False)
    # Chave canônica do estabelecimento — é ela que identifica a série,
    # não a descrição (que muda de mês em mês em vários bancos).
    merchant_key = Column(String, nullable=False)
    description = Column(String, nullable=True)

    amount = Column(Float, nullable=False)
    next_due_date = Column(DateTime(timezone=True), nullable=True)
    occurrences = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)

    # JSON com o metadata cru do detector (mesma convenção do projeto)
    detector_metadata = Column(Text, nullable=True)

    active = Column(Boolean, nullable=False, default=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_shadow_invoices_user_type", "user_id", "type", "active"),
        Index("idx_shadow_invoices_user_merchant", "user_id", "merchant_key", "type"),
    )
