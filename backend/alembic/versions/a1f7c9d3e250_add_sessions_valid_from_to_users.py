"""add sessions_valid_from to users — revogação global de sessão

Corte de sessão por usuário: todo token com `iat` anterior a este instante é
rejeitado em `security.sessao_invalidada`. É o que faz "trocar a senha derrubar
as sessões abertas" funcionar — sem ele, um token roubado sobrevivia ao reset
por até 30 min (access) ou 14 DIAS (refresh).

Nulo para contas existentes: nunca houve corte, então nada é invalidado
retroativamente pela migração.

Revision ID: a1f7c9d3e250
Revises: f7a2d94c6b18
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f7c9d3e250"
down_revision: Union[str, Sequence[str], None] = "f7a2d94c6b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_valid_from")
