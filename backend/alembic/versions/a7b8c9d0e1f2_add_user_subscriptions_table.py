"""add_user_subscriptions_table

Revision ID: a7b8c9d0e1f2
Revises: c2d4f6a8b0e1
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'c2d4f6a8b0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", sa.String(100), primary_key=True),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_id", sa.String(100), nullable=True),
    )
    op.create_index("ix_user_subscriptions_stripe_customer_id", "user_subscriptions", ["stripe_customer_id"])
    op.create_index("ix_user_subscriptions_stripe_subscription_id", "user_subscriptions", ["stripe_subscription_id"])
    op.create_index("ix_user_subscriptions_plan_status", "user_subscriptions", ["plan", "status"])


def downgrade() -> None:
    op.drop_index("ix_user_subscriptions_plan_status", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_stripe_subscription_id", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_stripe_customer_id", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
