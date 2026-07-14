"""add bingo history tables

Revision ID: a1b2c3d4e5f6
Revises: 28bfe244cb65
Create Date: 2026-07-14 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '28bfe244cb65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bingo_games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_code", sa.String(length=20), nullable=False),
        sa.Column("room_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("board_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_boards", sa.Integer(), nullable=False),
        sa.Column("total_players", sa.Integer(), nullable=False),
        sa.Column("derash", sa.Numeric(12, 2), nullable=False),
        sa.Column("winning_pattern", sa.String(length=40), nullable=True),
        sa.Column("winner_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bingo_games_game_code"),
        "bingo_games",
        ["game_code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_bingo_games_room_id"),
        "bingo_games",
        ["room_id"],
        unique=False,
    )

    op.create_table(
        "bingo_game_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("boards_count", sa.Integer(), nullable=False),
        sa.Column("stake_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.Column("amount_won", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["bingo_games.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bingo_game_results_game_id"),
        "bingo_game_results",
        ["game_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bingo_game_results_user_id"),
        "bingo_game_results",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_bingo_game_results_user_id"),
        table_name="bingo_game_results",
    )
    op.drop_index(
        op.f("ix_bingo_game_results_game_id"),
        table_name="bingo_game_results",
    )
    op.drop_table("bingo_game_results")
    op.drop_index(op.f("ix_bingo_games_room_id"), table_name="bingo_games")
    op.drop_index(op.f("ix_bingo_games_game_code"), table_name="bingo_games")
    op.drop_table("bingo_games")
