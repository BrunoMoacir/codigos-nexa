"""add_intelligence_metrics_table

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_metrics",
        sa.Column("metric_date", sa.Date(), primary_key=True),
        sa.Column("metric_key", sa.String(60), primary_key=True),
        sa.Column("dimension", sa.String(60), primary_key=True, server_default="_"),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_intelligence_metrics_key_date", "intelligence_metrics",
        ["metric_key", "metric_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_metrics_key_date", table_name="intelligence_metrics")
    op.drop_table("intelligence_metrics")
