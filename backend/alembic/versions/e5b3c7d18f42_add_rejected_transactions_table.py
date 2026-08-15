"""add rejected_transactions table (DLQ da ingestão Open Finance)

Antes desta tabela, transação recusada pelo firewall Pydantic existia só na
memória do request: um conector degradando em produção era invisível — o
usuário via menos lançamentos e não havia como saber por quê nem
reprocessar. Agora cada rejeição fica com payload cru + erro por campo.

Revision ID: e5b3c7d18f42
Revises: d4e7f1a90b2c
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b3c7d18f42"
down_revision: Union[str, Sequence[str], None] = "d4e7f1a90b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rejected_transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=True, index=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("institution_id", sa.String(), nullable=True),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("field_errors", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=False),
        sa.Column("raw_data_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "idx_rejected_institution_date",
        "rejected_transactions",
        ["institution_id", "rejected_at"],
    )
    op.create_index(
        "idx_rejected_user_date",
        "rejected_transactions",
        ["user_id", "rejected_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_rejected_user_date", table_name="rejected_transactions")
    op.drop_index("idx_rejected_institution_date", table_name="rejected_transactions")
    op.drop_table("rejected_transactions")
