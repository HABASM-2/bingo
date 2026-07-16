"""add dama games history tables

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-16 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dama_games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_code", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("pot", sa.Numeric(12, 2), nullable=False),
        sa.Column("system_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("prize_pool", sa.Numeric(12, 2), nullable=False),
        sa.Column("match_id", sa.String(length=64), nullable=True),
        sa.Column("winner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("winner_side", sa.String(length=10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_code"),
    )
    op.create_index("ix_dama_games_game_code", "dama_games", ["game_code"])
    op.create_index("ix_dama_games_match_id", "dama_games", ["match_id"])

    op.create_table(
        "dama_game_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stake_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.Column("amount_won", sa.Numeric(12, 2), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["dama_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dama_game_results_game_id", "dama_game_results", ["game_id"])
    op.create_index("ix_dama_game_results_user_id", "dama_game_results", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_dama_game_results_user_id", table_name="dama_game_results")
    op.drop_index("ix_dama_game_results_game_id", table_name="dama_game_results")
    op.drop_table("dama_game_results")
    op.drop_index("ix_dama_games_match_id", table_name="dama_games")
    op.drop_index("ix_dama_games_game_code", table_name="dama_games")
    op.drop_table("dama_games")
