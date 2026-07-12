"""Add push_subscriptions table (Web Push / PWA — R1.d)

Revision ID: c2d4f6a8b0e1
Revises: a7c9e5f2b1d8
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d4f6a8b0e1"
down_revision: Union[str, Sequence[str], None] = "a7c9e5f2b1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),      # URL do push service do navegador
        sa.Column("p256dh", sa.Text(), nullable=False),        # chave pública do cliente
        sa.Column("auth", sa.Text(), nullable=False),          # auth secret do cliente
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions"),
    )
    op.create_index("idx_push_subscriptions_user", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_push_subscriptions_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
