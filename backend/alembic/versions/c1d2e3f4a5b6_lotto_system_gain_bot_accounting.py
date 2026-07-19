"""add lotto system_gain and bot stake accounting columns

Revision ID: c1d2e3f4a5b6
Revises: a8b9c0d1e2f3
Create Date: 2026-07-19 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "system_gain",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "bot_won",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "real_stake_total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "lotto_rounds",
        sa.Column(
            "bot_stake_total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    # Legacy completed rounds: approximate gain from the 4% reserve (no bot split).
    op.execute(
        "UPDATE lotto_rounds SET system_gain = reserve_amount "
        "WHERE status = 'completed' AND system_gain = 0 AND reserve_amount <> 0"
    )


def downgrade() -> None:
    op.drop_column("lotto_rounds", "bot_stake_total")
    op.drop_column("lotto_rounds", "real_stake_total")
    op.drop_column("lotto_rounds", "bot_won")
    op.drop_column("lotto_rounds", "system_gain")
