"""add aviator rounds and bets tables

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-07-16 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aviator_rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_code", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("crash_multiplier", sa.Numeric(10, 4), nullable=True),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("total_stake", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_payout", sa.Numeric(14, 2), nullable=False),
        sa.Column("system_fee", sa.Numeric(14, 2), nullable=False),
        sa.Column("max_payout_mult", sa.Numeric(8, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_code"),
    )
    op.create_index("ix_aviator_rounds_round_code", "aviator_rounds", ["round_code"])

    op.create_table(
        "aviator_bets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("cashout_multiplier", sa.Numeric(10, 4), nullable=True),
        sa.Column("amount_won", sa.Numeric(12, 2), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["round_id"], ["aviator_rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aviator_bets_round_id", "aviator_bets", ["round_id"])
    op.create_index("ix_aviator_bets_user_id", "aviator_bets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_aviator_bets_user_id", table_name="aviator_bets")
    op.drop_index("ix_aviator_bets_round_id", table_name="aviator_bets")
    op.drop_table("aviator_bets")
    op.drop_index("ix_aviator_rounds_round_code", table_name="aviator_rounds")
    op.drop_table("aviator_rounds")
