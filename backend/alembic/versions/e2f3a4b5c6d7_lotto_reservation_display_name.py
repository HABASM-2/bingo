"""add lotto reservation display_name for public board labels

Revision ID: e2f3a4b5c6d7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-19 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lotto_reservations",
        sa.Column("display_name", sa.String(length=48), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lotto_reservations", "display_name")
