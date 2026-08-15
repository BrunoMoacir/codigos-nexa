"""add shadow_invoices table (obrigações futuras detectadas)

O Step 5 do ETL detectava assinaturas e parcelamentos e descartava o
resultado (TODO no runner). Sem persistir, cada consulta reprocessava todo
o histórico para redescobrir o mesmo, e não havia como comparar o previsto
com o que de fato caiu no mês seguinte.

Revision ID: f7a2d94c6b18
Revises: e5b3c7d18f42
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a2d94c6b18"
down_revision: Union[str, Sequence[str], None] = "e5b3c7d18f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shadow_invoices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("next_due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrences", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("detector_metadata", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "idx_shadow_invoices_user_type", "shadow_invoices", ["user_id", "type", "active"]
    )
    op.create_index(
        "idx_shadow_invoices_user_merchant",
        "shadow_invoices",
        ["user_id", "merchant_key", "type"],
    )


def downgrade() -> None:
    op.drop_index("idx_shadow_invoices_user_merchant", table_name="shadow_invoices")
    op.drop_index("idx_shadow_invoices_user_type", table_name="shadow_invoices")
    op.drop_table("shadow_invoices")
