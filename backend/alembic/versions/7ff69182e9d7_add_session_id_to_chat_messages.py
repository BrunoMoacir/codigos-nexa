"""add_session_id_to_chat_messages

Revision ID: 7ff69182e9d7
Revises: 9b6f8e1c4d20
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7ff69182e9d7'
down_revision: Union[str, Sequence[str], None] = '9b6f8e1c4d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('session_id', sa.String(length=100), nullable=True))
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_chat_messages_session_id', table_name='chat_messages')
    op.drop_column('chat_messages', 'session_id')
