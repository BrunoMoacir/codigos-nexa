"""add_credit_cards_table

Revision ID: b3e8a1c7f0d4
Revises: 7ff69182e9d7
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3e8a1c7f0d4'
down_revision: Union[str, Sequence[str], None] = '7ff69182e9d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'credit_cards',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('item_id', sa.String(), nullable=True),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('bank_name', sa.String(), nullable=True),
        sa.Column('brand', sa.String(), nullable=True),
        sa.Column('level', sa.String(), nullable=True),
        sa.Column('last4', sa.String(), nullable=True),
        sa.Column('credit_limit', sa.Float(), nullable=True),
        sa.Column('available_credit_limit', sa.Float(), nullable=True),
        sa.Column('balance_close_date', sa.String(), nullable=True),
        sa.Column('balance_due_date', sa.String(), nullable=True),
        sa.Column('currency', sa.String(), nullable=False, server_default='BRL'),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_credit_cards_user_id', 'credit_cards', ['user_id'])
    op.create_index('idx_credit_cards_user', 'credit_cards', ['user_id', 'captured_at'])


def downgrade() -> None:
    op.drop_index('idx_credit_cards_user', table_name='credit_cards')
    op.drop_index('ix_credit_cards_user_id', table_name='credit_cards')
    op.drop_table('credit_cards')
