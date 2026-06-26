"""add_nexa_roadmap_tables

Revision ID: e1a2b3c4d5f6
Revises: f3a2b1c0d4e5
Create Date: 2026-06-26 00:00:00.000000

Tabelas adicionadas (itens 2.1–2.8 do MUDANÇAS.md):
  - bank_fee_history        — histórico de tarifas por usuário (D1/D2/D4)
  - bank_fee_trends         — baseline de mercado por banco (D4/D2)
  - notification_delivery_log — log de entrega de notificações (MX.3/R1.c/R5.c)
  - daily_digest_log        — controle de idempotência de digests (R1.c)
  - user_badges             — badges e gamificação (R2.b)
  - user_settings           — preferências de canal/frequência (MX.3/R1.c/R5.b)
  - negotiation_history     — histórico de negociações F13 (F13/D4 follow-up)
  - opportunity_snapshots   — histórico do radar de oportunidades (OPP/V2)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "f3a2b1c0d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 2.1 — Histórico de tarifas cobradas por usuário
    op.create_table(
        "bank_fee_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),      # "YYYY-MM"
        sa.Column("bank_name", sa.String(), nullable=False),
        sa.Column("fee_type", sa.String(), nullable=False),    # FeeType enum
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "month", "bank_name", "fee_type", name="uq_bank_fee_history"),
    )
    op.create_index("idx_bank_fee_history_user", "bank_fee_history", ["user_id", "month"])

    # 2.2 — Baseline de mercado por banco/tipo de tarifa
    op.create_table(
        "bank_fee_trends",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bank_name", sa.String(), nullable=False),
        sa.Column("fee_type", sa.String(), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("market_avg", sa.Numeric(10, 2), nullable=True),
        sa.Column("market_p25", sa.Numeric(10, 2), nullable=True),
        sa.Column("market_p75", sa.Numeric(10, 2), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("bank_name", "fee_type", "month", name="uq_bank_fee_trends"),
    )

    # 2.3 — Log de entrega de notificações (auditoria + retry)
    op.create_table(
        "notification_delivery_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("notification_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),     # "email" | "push" | "in_app"
        sa.Column("status", sa.String(), nullable=False),      # "sent" | "delivered" | "failed" | "opened"
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_notif_delivery_user", "notification_delivery_log", ["user_id"])
    op.create_index("idx_notif_delivery_notif_id", "notification_delivery_log", ["notification_id"])

    # 2.4 — Controle de idempotência de digests diários
    op.create_table(
        "daily_digest_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("events_qty", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "date", name="uq_daily_digest_log"),
    )

    # 2.5 — Badges de gamificação
    op.create_table(
        "user_badges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("badge_type", sa.String(), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),       # JSON serializado
        sa.UniqueConstraint("user_id", "badge_type", name="uq_user_badges"),
    )
    op.create_index("idx_user_badges_user", "user_badges", ["user_id"])

    # 2.6 — Preferências de canal e frequência de notificação
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column(
            "notification_channels",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'[\"email\"]'"),  # JSON array como texto
        ),
        sa.Column("notification_frequency", sa.String(), nullable=True, server_default=sa.text("'daily'")),
        sa.Column("digest_time", sa.String(5), nullable=True, server_default=sa.text("'07:00'")),
        sa.Column("subscription_status", sa.String(), nullable=True, server_default=sa.text("'active'")),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    # 2.7 — Histórico de negociações para follow-up F13
    op.create_table(
        "negotiation_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("bank_name", sa.String(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False),  # NegotiationTrigger enum
        sa.Column("potential_gain", sa.Numeric(10, 2), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_status", sa.String(), nullable=True),  # "sucesso"|"parcial"|"recusado"|"nao_tentou"
        sa.Column("result_gain", sa.Numeric(10, 2), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_negotiation_history_user", "negotiation_history", ["user_id", "generated_at"])

    # 2.8 — Snapshots do radar de oportunidades
    op.create_table(
        "opportunity_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_loss", sa.Numeric(10, 2), nullable=True),
        sa.Column("top_opportunity", sa.String(), nullable=True),   # banco recomendado
        sa.Column("top_gain_brl", sa.Numeric(10, 2), nullable=True),
        sa.Column("cdi_at_capture", sa.Numeric(5, 4), nullable=True),
    )
    op.create_index("idx_opp_snapshots_user", "opportunity_snapshots", ["user_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("idx_opp_snapshots_user", table_name="opportunity_snapshots")
    op.drop_table("opportunity_snapshots")

    op.drop_index("idx_negotiation_history_user", table_name="negotiation_history")
    op.drop_table("negotiation_history")

    op.drop_table("user_settings")

    op.drop_index("idx_user_badges_user", table_name="user_badges")
    op.drop_table("user_badges")

    op.drop_table("daily_digest_log")

    op.drop_index("idx_notif_delivery_notif_id", table_name="notification_delivery_log")
    op.drop_index("idx_notif_delivery_user", table_name="notification_delivery_log")
    op.drop_table("notification_delivery_log")

    op.drop_table("bank_fee_trends")

    op.drop_index("idx_bank_fee_history_user", table_name="bank_fee_history")
    op.drop_table("bank_fee_history")
