"""eventos do webhook Stripe já processados (idempotência por event id)

Revision ID: c5e1b7a9d3f2
Revises: 84dbb59343ed
Create Date: 2026-11-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5e1b7a9d3f2'
down_revision: Union[str, Sequence[str], None] = '84dbb59343ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("event_id", sa.String(100), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("billing_webhook_events")
