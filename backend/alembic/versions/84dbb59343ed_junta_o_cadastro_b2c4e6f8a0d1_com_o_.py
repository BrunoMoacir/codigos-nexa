"""junta o cadastro (b2c4e6f8a0d1) com o ramo de cartões e sessões do chat (b3e8a1c7f0d4)

Revision ID: 84dbb59343ed
Revises: b2c4e6f8a0d1, b3e8a1c7f0d4
Create Date: 2026-10-05 17:11:59.012837

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '84dbb59343ed'
down_revision: Union[str, Sequence[str], None] = ('b2c4e6f8a0d1', 'b3e8a1c7f0d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Só une os dois ramos — nenhuma mudança de schema."""


def downgrade() -> None:
    """Só une os dois ramos — nenhuma mudança de schema."""
