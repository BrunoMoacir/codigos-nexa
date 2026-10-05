"""cadastro com telefone e aceite de termos

Revision ID: b2c4e6f8a0d1
Revises: a1f7c9d3e250
Create Date: 2026-10-03

- users.phone / users.terms_accepted_at: o cadastro do app coletava telefone
  e aceite dos termos e o backend descartava os dois. O aceite é o registro
  do consentimento; o cadastro passa a exigi-lo.
- chat_messages.session_id fica com a migração 7ff69182e9d7 (do outro ramo,
  que chegou primeiro): as duas criavam a mesma coluna.
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


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "phone")
