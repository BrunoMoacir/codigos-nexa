"""cadastro com telefone e aceite de termos; histórico do chat por sessão

Revision ID: b2c4e6f8a0d1
Revises: a1f7c9d3e250
Create Date: 2026-10-03

- users.phone / users.terms_accepted_at: o cadastro do app coletava telefone
  e aceite dos termos e o backend descartava os dois. O aceite é o registro
  do consentimento; o cadastro passa a exigi-lo.
- chat_messages.session_id: o histórico era um só por usuário, enquanto a
  memória do agente é por dono+sessão — a tela mostrava conversas que o
  agente já não lembrava.
"""
from alembic import op
import sqlalchemy as sa


revision = "b2c4e6f8a0d1"
down_revision = "a1f7c9d3e250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chat_messages", sa.Column("session_id", sa.String(length=100), nullable=True))
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_column("chat_messages", "session_id")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "phone")
