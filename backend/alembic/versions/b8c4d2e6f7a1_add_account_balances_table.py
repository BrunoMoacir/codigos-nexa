"""add account_balances table

Snapshots de saldo real por conta (Pluggy) — base da personalização do OPP
com saldo real (poupança vs. CDI personalizado, tarifas reais no Bank Match).
Append-only: uma linha por conta por sync; o leitor usa sempre a mais recente.

Revision ID: b8c4d2e6f7a1
Revises: e1a2b3c4d5f6
Create Date: 2026-07-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c4d2e6f7a1"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_balances",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("bank_name", sa.String(), nullable=True),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="BRL"),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_account_balances_user_type",
        "account_balances",
        ["user_id", "account_type", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_account_balances_user_type", table_name="account_balances")
    op.drop_table("account_balances")
