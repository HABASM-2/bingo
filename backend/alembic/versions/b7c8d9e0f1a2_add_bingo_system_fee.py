"""add bingo system_fee column

Revision ID: b7c8d9e0f1a2
Revises: 80e9d998aec2
Create Date: 2026-07-16 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "80e9d998aec2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bingo_games",
        sa.Column(
            "system_fee",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("bingo_games", "system_fee")
