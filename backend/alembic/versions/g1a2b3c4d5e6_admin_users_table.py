"""create admin_users table for multi-admin management

Revision ID: g1a2b3c4d5e6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-19 19:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_admin_users_username"),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_admin_users_username", table_name="admin_users")
    op.drop_table("admin_users")
