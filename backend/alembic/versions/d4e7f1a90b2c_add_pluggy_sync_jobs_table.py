"""add pluggy_sync_jobs table

Estado durável do sync assíncrono da Pluggy (app/pluggy_sync). É a fonte da
verdade do long-polling e do SSE: `version` é o cursor que o cliente devolve
para receber só o que mudou desde a última leitura — inclusive quando o
worker que atende o poll não é o que roda o job.

Esta revisão também faz o merge dos dois heads que existiam
(c1d2e3f4a5b6 e f1a2c3d4e5b6), para `alembic upgrade head` voltar a
funcionar sem ambiguidade.

Revision ID: d4e7f1a90b2c
Revises: c1d2e3f4a5b6, f1a2c3d4e5b6
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e7f1a90b2c"
down_revision: Union[str, Sequence[str], None] = ("c1d2e3f4a5b6", "f1a2c3d4e5b6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pluggy_sync_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("phase", sa.String(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_pluggy_sync_jobs_user_created",
        "pluggy_sync_jobs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_pluggy_sync_jobs_user_created", table_name="pluggy_sync_jobs")
    op.drop_table("pluggy_sync_jobs")
