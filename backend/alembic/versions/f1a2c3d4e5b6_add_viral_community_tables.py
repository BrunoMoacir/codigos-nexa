"""add_viral_community_tables

Revision ID: f1a2c3d4e5b6
Revises: c2d4f6a8b0e1
Create Date: 2026-07-15 00:00:00.000000

Tabelas adicionadas (Viral V2 + Comunidade):
  - viral_share_log             — eventos de compartilhamento (badge VIRAL_SHARE, CAC viral)
  - viral_calculation_snapshots — snapshot imutável do cálculo publicado (contestabilidade)
  - viral_ranking_snapshots     — ranking trimestral V3 (a popular quando V3 estiver pronto)
  - viral_consent_receipts      — prova de consentimento quando base legal for consentimento
  - community_posts             — feed de comunidade (posts com pseudônimo)
  - community_reactions         — reações (hash de user_id, sem PII)
  - community_reports           — denúncias de conteúdo
  - community_moderation_log    — trilha de decisão de moderação
  - community_challenges        — desafios financeiros opt-in
  - community_memberships       — adesão à comunidade com versão dos termos
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2c3d4e5b6"
down_revision: Union[str, Sequence[str], None] = "c2d4f6a8b0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── viral_share_log ──────────────────────────────────────────────
    op.create_table(
        "viral_share_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("card_type", sa.String(32), nullable=False),   # savings_card | wrapped
        sa.Column("channel", sa.String(64), nullable=False),     # whatsapp | instagram | link | etc.
        sa.Column("card_version", sa.String(16), nullable=False, server_default="2.0"),
        sa.Column("utm_campaign", sa.String(128), nullable=True),
        sa.Column("utm_medium", sa.String(64), nullable=True),
        sa.Column("shared_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_viral_share_log_user_shared", "viral_share_log", ["user_id", "shared_at"])

    # ── viral_calculation_snapshots ──────────────────────────────────
    op.create_table(
        "viral_calculation_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("card_type", sa.String(32), nullable=False),
        sa.Column("calculation_version", sa.String(16), nullable=False),
        sa.Column("total_brl", sa.Numeric(14, 2), nullable=False),
        sa.Column("sources_json", sa.Text, nullable=True),      # JSON serializado dos sources
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("year", sa.Integer, nullable=True),           # só para wrapped
    )

    # ── viral_ranking_snapshots ──────────────────────────────────────
    op.create_table(
        "viral_ranking_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quarter", sa.String(7), nullable=False),     # '2026-Q3'
        sa.Column("bank_name", sa.String(128), nullable=False),
        sa.Column("cnpj8", sa.String(8), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("d2_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("d3_multiple", sa.Numeric(5, 2), nullable=True),
        sa.Column("d4_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("bacen_rank", sa.Integer, nullable=True),
        sa.Column("nao_resolucao", sa.Numeric(5, 4), nullable=True),
        sa.Column("sample_size", sa.Integer, nullable=True),
        sa.Column("methodology_version", sa.String(16), nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("quarter", "bank_name", name="uq_viral_ranking_quarter_bank"),
    )

    # ── viral_consent_receipts ───────────────────────────────────────
    op.create_table(
        "viral_consent_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("purpose", sa.String(64), nullable=False),    # 'share_v1' | 'share_v2' | 'community'
        sa.Column("granted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("terms_version", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(64), nullable=True),
    )

    # ── community_memberships ────────────────────────────────────────
    op.create_table(
        "community_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True),
        sa.Column("pseudonym_id", sa.String(36), nullable=False, unique=True),
        sa.Column("terms_version", sa.String(16), nullable=False),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        # status: active | suspended | banned | left
    )

    # ── community_posts ──────────────────────────────────────────────
    op.create_table(
        "community_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_type", sa.String(16), nullable=False),  # nexa | specialist | member
        sa.Column("pseudonym_id", sa.String(36), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("topic", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        # status: active | under_review | removed | author_deleted
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("moderated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_community_posts_topic_status", "community_posts", ["topic", "status"])

    # ── community_reactions ──────────────────────────────────────────
    op.create_table(
        "community_reactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("post_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id_hash", sa.String(64), nullable=False),  # sha256 — sem PII
        sa.Column("reaction_type", sa.String(32), nullable=False),  # util | aprendi | quero_entender
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("post_id", "user_id_hash", "reaction_type", name="uq_community_reaction"),
    )

    # ── community_reports ────────────────────────────────────────────
    op.create_table(
        "community_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), nullable=False, index=True),
        sa.Column("reporter_id", sa.String(36), nullable=False),  # pseudonym_id
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # status: pending | under_review | resolved | dismissed
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── community_moderation_log ─────────────────────────────────────
    op.create_table(
        "community_moderation_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), nullable=False, index=True),
        sa.Column("rule_version", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),  # remove | warn | dismiss | escalate
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("actor", sa.String(64), nullable=False),   # 'system' | moderator_id
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── community_challenges ─────────────────────────────────────────
    op.create_table(
        "community_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("behavior", sa.String(128), nullable=False),  # ex: 'reduzir_tarifa'
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("eligibility", sa.Text, nullable=True),       # JSON com critérios
        sa.Column("privacy_mode", sa.String(16), nullable=False, server_default="anonymous"),
        # privacy_mode: anonymous | opt_in_public
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("community_challenges")
    op.drop_table("community_moderation_log")
    op.drop_table("community_reports")
    op.drop_table("community_reactions")
    op.drop_table("community_posts")
    op.drop_table("community_memberships")
    op.drop_table("viral_consent_receipts")
    op.drop_table("viral_ranking_snapshots")
    op.drop_table("viral_calculation_snapshots")
    op.drop_table("viral_share_log")
