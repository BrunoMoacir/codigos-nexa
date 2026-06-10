"""add_recommendation_feedback_table

Revision ID: f3a2b1c0d4e5
Revises: d9e2f4a18c05
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a2b1c0d4e5'
down_revision: Union[str, Sequence[str], None] = 'd9e2f4a18c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id", sa.String(100), nullable=False, index=True),
        sa.Column("insight_type", sa.String(50), nullable=False, index=True),
        sa.Column("detector", sa.String(100), nullable=False),
        sa.Column("signals_json", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_feedback")
