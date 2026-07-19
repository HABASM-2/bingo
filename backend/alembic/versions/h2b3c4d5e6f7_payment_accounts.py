"""add payment_accounts and withdraw paid_from_account_id

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-07-19 20:45:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Seed matches the previous hardcoded bot DEPOSIT_METHODS placeholders.
_SEED_DEPOSITS = [
    ("Telebirr", "Telegram Games", "0912345678", 10),
    ("CBE", "Telegram Games", "1000123456789", 20),
    ("CBE Birr", "Telegram Games", "0911111111", 30),
    ("Bank of Abyssinia", "Telegram Games", "1234567890", 40),
]


def upgrade() -> None:
    op.create_table(
        "payment_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("bank", sa.String(length=80), nullable=False),
        sa.Column("account_name", sa.String(length=150), nullable=False),
        sa.Column("account_number", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kind", "bank", "account_number",
            name="uq_payment_accounts_kind_bank_number",
        ),
    )
    op.create_index("ix_payment_accounts_kind", "payment_accounts", ["kind"], unique=False)

    op.add_column(
        "withdraw_requests",
        sa.Column("paid_from_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_withdraw_requests_paid_from_account_id",
        "withdraw_requests",
        "payment_accounts",
        ["paid_from_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    accounts = sa.table(
        "payment_accounts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("kind", sa.String),
        sa.column("bank", sa.String),
        sa.column("account_name", sa.String),
        sa.column("account_number", sa.String),
        sa.column("is_enabled", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    rows = []
    for bank, name, number, order in _SEED_DEPOSITS:
        rows.append(
            {
                "id": uuid.uuid4(),
                "kind": "deposit",
                "bank": bank,
                "account_name": name,
                "account_number": number,
                "is_enabled": True,
                "sort_order": order,
            }
        )
        rows.append(
            {
                "id": uuid.uuid4(),
                "kind": "withdraw",
                "bank": bank,
                "account_name": name,
                "account_number": number,
                "is_enabled": True,
                "sort_order": order,
            }
        )
    op.bulk_insert(accounts, rows)


def downgrade() -> None:
    op.drop_constraint(
        "fk_withdraw_requests_paid_from_account_id",
        "withdraw_requests",
        type_="foreignkey",
    )
    op.drop_column("withdraw_requests", "paid_from_account_id")
    op.drop_index("ix_payment_accounts_kind", table_name="payment_accounts")
    op.drop_table("payment_accounts")
