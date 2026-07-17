"""expand lotto capacity to 25 and 60/24/12/4 split

Revision ID: b2c3d4e5f6a7
Revises: f0a1b2c3d4e5
Create Date: 2026-07-17 16:20:00.000000

Historical completed rounds keep stored prize amounts and capacity=20.
Open rounds are upgraded to capacity=25 with the new prize split.
Countdown/drawing rounds already in flight keep their stored prizes.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAPACITY = 25
MONEY = Decimal("0.01")


def _prize_math(stake: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    stake = Decimal(stake).quantize(MONEY)
    pool = (stake * CAPACITY).quantize(MONEY)
    first = (pool * Decimal("0.60")).quantize(MONEY, rounding=ROUND_DOWN)
    second = (pool * Decimal("0.24")).quantize(MONEY, rounding=ROUND_DOWN)
    third = (pool * Decimal("0.12")).quantize(MONEY, rounding=ROUND_DOWN)
    system = (pool - first - second - third).quantize(MONEY)
    return pool, first, second, third, system


def upgrade() -> None:
    op.drop_constraint("ck_lotto_round_capacity", "lotto_rounds", type_="check")
    op.drop_constraint("ck_lotto_reservation_number", "lotto_reservations", type_="check")
    op.drop_constraint("ck_lotto_winner_number", "lotto_winners", type_="check")

    op.create_check_constraint(
        "ck_lotto_round_capacity",
        "lotto_rounds",
        "capacity IN (20, 25)",
    )
    op.create_check_constraint(
        "ck_lotto_reservation_number",
        "lotto_reservations",
        "number BETWEEN 1 AND 25",
    )
    op.create_check_constraint(
        "ck_lotto_winner_number",
        "lotto_winners",
        "number BETWEEN 1 AND 25",
    )

    rounds = sa.table(
        "lotto_rounds",
        sa.column("id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("room_stake", sa.Numeric(12, 2)),
        sa.column("capacity", sa.Integer()),
        sa.column("total_pool", sa.Numeric(12, 2)),
        sa.column("first_prize", sa.Numeric(12, 2)),
        sa.column("second_prize", sa.Numeric(12, 2)),
        sa.column("third_prize", sa.Numeric(12, 2)),
        sa.column("reserve_amount", sa.Numeric(12, 2)),
    )
    conn = op.get_bind()
    open_rounds = conn.execute(
        sa.select(rounds.c.id, rounds.c.room_stake).where(rounds.c.status == "open")
    ).fetchall()
    for row in open_rounds:
        pool, first, second, third, system = _prize_math(Decimal(str(row.room_stake)))
        conn.execute(
            rounds.update()
            .where(rounds.c.id == row.id)
            .values(
                capacity=CAPACITY,
                total_pool=pool,
                first_prize=first,
                second_prize=second,
                third_prize=third,
                reserve_amount=system,
            )
        )


def downgrade() -> None:
    op.drop_constraint("ck_lotto_round_capacity", "lotto_rounds", type_="check")
    op.drop_constraint("ck_lotto_reservation_number", "lotto_reservations", type_="check")
    op.drop_constraint("ck_lotto_winner_number", "lotto_winners", type_="check")

    op.execute(
        sa.text(
            "UPDATE lotto_rounds SET capacity = 20 "
            "WHERE status = 'open' AND capacity = 25"
        )
    )

    op.create_check_constraint(
        "ck_lotto_round_capacity",
        "lotto_rounds",
        "capacity = 20",
    )
    op.create_check_constraint(
        "ck_lotto_reservation_number",
        "lotto_reservations",
        "number BETWEEN 1 AND 20",
    )
    op.create_check_constraint(
        "ck_lotto_winner_number",
        "lotto_winners",
        "number BETWEEN 1 AND 20",
    )
