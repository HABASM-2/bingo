"""add bingo system_gain and bot stake accounting columns

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-18 22:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bingo_games",
        sa.Column(
            "system_gain",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "bingo_games",
        sa.Column(
            "bot_won",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "bingo_games",
        sa.Column(
            "real_stake_total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "bingo_games",
        sa.Column(
            "bot_stake_total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    # Backfill admin gain from legacy prize-facing fee for finished rounds.
    op.execute(
        "UPDATE bingo_games SET system_gain = system_fee "
        "WHERE system_gain = 0 AND system_fee <> 0"
    )


def downgrade() -> None:
    op.drop_column("bingo_games", "bot_stake_total")
    op.drop_column("bingo_games", "real_stake_total")
    op.drop_column("bingo_games", "bot_won")
    op.drop_column("bingo_games", "system_gain")
