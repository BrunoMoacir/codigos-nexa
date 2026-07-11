"""Add user_challenges table (R2.b) e merge dos heads b8c4d2e6f7a1 + 9b6f8e1c4d20

O repositório tinha dois heads paralelos desde que 9b6f8e1c4d20 (is_active em
users) foi criada a partir de c7f1e9a02b3d em vez do head da época. Esta
revisão faz o merge das duas linhas e cria a tabela de desafios mensais.

Revision ID: a7c9e5f2b1d8
Revises: b8c4d2e6f7a1, 9b6f8e1c4d20
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c9e5f2b1d8"
down_revision: Union[str, Sequence[str], None] = ("b8c4d2e6f7a1", "9b6f8e1c4d20")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria a tabela de desafios mensais do Health Score (R2.b)."""
    op.create_table(
        "user_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("challenge_type", sa.String(), nullable=False),   # SEM_TARIFAS | REDUZIR_CATEGORIA | GUARDAR_VALOR | SUBIR_SCORE
        sa.Column("month", sa.String(7), nullable=False),           # "YYYY-MM"
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("target_label", sa.String(), nullable=True),
        sa.Column("target_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("progress_value", sa.Numeric(12, 2), nullable=True, server_default=sa.text("0")),
        sa.Column("pct_progress", sa.Numeric(5, 1), nullable=True, server_default=sa.text("0")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),  # ACTIVE | COMPLETED | FAILED
        sa.Column("metadata", sa.Text(), nullable=True),            # JSON serializado (baseline, categoria, etc.)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "challenge_type", "month", name="uq_user_challenges"),
    )
    op.create_index("idx_user_challenges_user_month", "user_challenges", ["user_id", "month"])


def downgrade() -> None:
    op.drop_index("idx_user_challenges_user_month", table_name="user_challenges")
    op.drop_table("user_challenges")
