"""admin list query indexes for scalable filters

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-17 21:40:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_withdraw_requests_status_created",
        "withdraw_requests",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_withdraw_requests_created_at",
        "withdraw_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_deposits_created_at",
        "deposits",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_deposits_user_created",
        "deposits",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_users_created_at",
        "users",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_deposits_user_created", table_name="deposits")
    op.drop_index("ix_deposits_created_at", table_name="deposits")
    op.drop_index("ix_withdraw_requests_created_at", table_name="withdraw_requests")
    op.drop_index("ix_withdraw_requests_status_created", table_name="withdraw_requests")
