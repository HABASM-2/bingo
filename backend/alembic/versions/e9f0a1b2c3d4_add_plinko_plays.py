"""add plinko plays

Revision ID: e9f0a1b2c3d4
Revises: d4e5f6a7b8c9
Create Date: 2026-07-17 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plinko_plays",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("risk", sa.String(10), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("multiplier", sa.Numeric(12, 4), nullable=False),
        sa.Column("payout", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_result", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plinko_plays_user_id", "plinko_plays", ["user_id"])
    op.create_index(
        "ix_plinko_plays_user_created",
        "plinko_plays",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_plinko_plays_user_created", table_name="plinko_plays")
    op.drop_index("ix_plinko_plays_user_id", table_name="plinko_plays")
    op.drop_table("plinko_plays")
