"""add persistent lotto spin

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-17 14:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lotto_rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("round_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("total_pool", sa.Numeric(12, 2), nullable=False),
        sa.Column("first_prize", sa.Numeric(12, 2), nullable=False),
        sa.Column("second_prize", sa.Numeric(12, 2), nullable=False),
        sa.Column("third_prize", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserve_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("countdown_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("draw_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drawing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("capacity = 20", name="ck_lotto_round_capacity"),
        sa.CheckConstraint(
            "stake_room IN (10, 25, 50, 100)".replace("stake_room", "room_stake"),
            name="ck_lotto_round_stake",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'countdown', 'drawing', 'completed', 'cancelled')",
            name="ck_lotto_round_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_code"),
    )
    op.create_index(
        "ix_lotto_rounds_stake_created",
        "lotto_rounds",
        ["room_stake", "created_at"],
    )
    op.create_index(
        "uq_lotto_round_active_stake",
        "lotto_rounds",
        ["room_stake"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'countdown', 'drawing')"),
    )

    op.create_table(
        "lotto_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "number BETWEEN 1 AND 20", name="ck_lotto_reservation_number"
        ),
        sa.ForeignKeyConstraint(
            ["round_id"], ["lotto_rounds.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "round_id", "number", name="uq_lotto_reservation_number"
        ),
    )
    op.create_index(
        "ix_lotto_reservation_round_user",
        "lotto_reservations",
        ["round_id", "user_id"],
    )

    op.create_table(
        "lotto_reservation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("numbers_csv", sa.String(80), nullable=False),
        sa.Column("charged_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "wallet_transaction_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["round_id"], ["lotto_rounds.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["wallet_transaction_id"], ["wallet_transactions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_id", name="uq_lotto_request_user_key"
        ),
    )

    op.create_table(
        "lotto_winners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prize", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "payout_transaction_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_lotto_winner_rank"),
        sa.CheckConstraint("number BETWEEN 1 AND 20", name="ck_lotto_winner_number"),
        sa.ForeignKeyConstraint(
            ["round_id"], ["lotto_rounds.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["payout_transaction_id"], ["wallet_transactions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "number", name="uq_lotto_winner_number"),
        sa.UniqueConstraint("round_id", "rank", name="uq_lotto_winner_rank"),
    )


def downgrade() -> None:
    op.drop_table("lotto_winners")
    op.drop_table("lotto_reservation_requests")
    op.drop_index("ix_lotto_reservation_round_user", table_name="lotto_reservations")
    op.drop_table("lotto_reservations")
    op.drop_index("uq_lotto_round_active_stake", table_name="lotto_rounds")
    op.drop_index("ix_lotto_rounds_stake_created", table_name="lotto_rounds")
    op.drop_table("lotto_rounds")
