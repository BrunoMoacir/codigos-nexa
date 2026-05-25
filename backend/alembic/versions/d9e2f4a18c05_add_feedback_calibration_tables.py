"""add_feedback_calibration_tables

Revision ID: d9e2f4a18c05
Revises: c7f1e9a02b3d
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e2f4a18c05'
down_revision: Union[str, Sequence[str], None] = 'c7f1e9a02b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "architect_simulation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("simulation_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id", sa.String(100), nullable=False, index=True),
        sa.Column("feedback_followed", sa.Boolean(), nullable=False),
        sa.Column("strategy_used", sa.String(20), nullable=False),
        sa.Column("npv_deviation", sa.Float(), nullable=True),
        sa.Column("rate_deviation", sa.Float(), nullable=True),
        sa.Column("actual_contemplation_month", sa.Integer(), nullable=True),
        sa.Column("actual_rate_obtained", sa.Float(), nullable=True),
        sa.Column("risk_score_at_simulation", sa.Float(), nullable=True),
        sa.Column("risk_profile_at_simulation", sa.String(20), nullable=True),
        sa.Column("confidence_score_at_simulation", sa.Float(), nullable=True),
        sa.Column("asset_type", sa.String(20), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "architect_calibration_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("threshold_conservative", sa.Float(), nullable=False, server_default="0.35"),
        sa.Column("threshold_aggressive", sa.Float(), nullable=False, server_default="0.65"),
        sa.Column("bid_params_json", sa.Text(), nullable=True),
        sa.Column("confidence_threshold_upper", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("previous_threshold_conservative", sa.Float(), nullable=True),
        sa.Column("previous_threshold_aggressive", sa.Float(), nullable=True),
        sa.Column("previous_bid_params_json", sa.Text(), nullable=True),
        sa.Column("previous_confidence_threshold_upper", sa.Float(), nullable=True),
        sa.Column("n_feedbacks_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_calibrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("architect_calibration_state")
    op.drop_table("architect_simulation_feedback")
