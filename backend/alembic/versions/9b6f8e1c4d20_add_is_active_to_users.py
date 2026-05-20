"""add is_active to users

Revision ID: 9b6f8e1c4d20
Revises: c7f1e9a02b3d
Create Date: 2026-05-18 13:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b6f8e1c4d20"
down_revision: Union[str, Sequence[str], None] = "c7f1e9a02b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")