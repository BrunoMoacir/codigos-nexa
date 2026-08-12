from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base

# ── Estados do job ────────────────────────────────────────────────────
JOB_PENDING = "PENDING"    # criado, ainda não começou
JOB_RUNNING = "RUNNING"    # thread trabalhando
JOB_SUCCESS = "SUCCESS"    # todos os items sincronizados
JOB_PARTIAL = "PARTIAL"    # ao menos um item falhou/expirou, outros ok
JOB_ERROR = "ERROR"        # nada foi sincronizado
JOB_TERMINAL = frozenset({JOB_SUCCESS, JOB_PARTIAL, JOB_ERROR})

# ── Fases (texto curto para a UI) ─────────────────────────────────────
PHASE_QUEUED = "queued"              # na fila
PHASE_WAITING_BANK = "waiting_bank"  # item UPDATING — banco ainda respondendo
PHASE_FETCHING = "fetching"          # baixando contas/transações da Pluggy
PHASE_PROCESSING = "processing"      # ETL (ingestor + classifier + persistência)
PHASE_DONE = "done"
PHASE_ERROR = "error"


class PluggySyncJob(Base):
    """Estado durável de uma sincronização Pluggy.

    É a fonte da verdade do long-polling e do SSE: cada mudança de estado
    incrementa `version`, que o cliente devolve como cursor. Assim uma
    reconexão (aba dormiu, wifi caiu, outro worker atendeu) retoma exatamente
    de onde parou, sem depender de estado em memória.
    """

    __tablename__ = "pluggy_sync_jobs"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)

    status = Column(String, nullable=False, default=JOB_PENDING)
    phase = Column(String, nullable=False, default=PHASE_QUEUED)
    progress = Column(Integer, nullable=False, default=0)  # 0-100
    message = Column(String, nullable=True)
    error = Column(String, nullable=True)

    # Cursor de long-polling: monotônico por job, incrementado a cada update.
    version = Column(Integer, nullable=False, default=0)

    items_total = Column(Integer, nullable=False, default=0)
    items_done = Column(Integer, nullable=False, default=0)
    accounts = Column(Integer, nullable=False, default=0)
    received = Column(Integer, nullable=False, default=0)
    valid = Column(Integer, nullable=False, default=0)
    saved = Column(Integer, nullable=False, default=0)

    # JSON com o detalhe por item (status, contadores, erro)
    detail = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pluggy_sync_jobs_user_created", "user_id", "created_at"),
    )
