"""add bingo_game_results.public_winner_name for bot dummy labels

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-18 20:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bingo_game_results",
        sa.Column("public_winner_name", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bingo_game_results", "public_winner_name")
