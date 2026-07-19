"""add lotto house_fee and bot_prizes accounting columns

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-19 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "bot_prizes",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "house_fee",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("lotto_rounds", "house_fee")
    op.drop_column("lotto_rounds", "bot_prizes")
