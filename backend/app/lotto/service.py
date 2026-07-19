"""Transactional Lotto Spin room, reservation, settlement, and history logic."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.lotto_game import (
    LottoReservation,
    LottoReservationRequest,
    LottoRound,
    LottoWinner,
)
from app.models.user import User
from app.services.wallet_service import credit_wallet

STAKES = (Decimal("10.00"), Decimal("25.00"), Decimal("50.00"), Decimal("100.00"))
CAPACITY = 25
FIRST_RATE = Decimal("0.60")
SECOND_RATE = Decimal("0.24")
THIRD_RATE = Decimal("0.12")
SYSTEM_RATE = Decimal("0.04")
assert FIRST_RATE + SECOND_RATE + THIRD_RATE + SYSTEM_RATE == Decimal("1")
ACTIVE_STATUSES = ("open", "countdown", "drawing")
MONEY = Decimal("0.01")
# Pre-draw window after the room fills: wait this long before locking winners.
COUNTDOWN_SECONDS = 60
# Gap between authoritative winner reveals. Must cover frontend anticipation
# (~1s) + cruise (~8s) + decelerate (~5s) + bounce/settle gap (~2–2.5s).
REVEAL_INTERVAL_SECONDS = 17.0
# Extra hold after the third reveal window so place→number→next.wav (+ pad)
# can finish before the round completes and the next open room appears.
# (~ third_winner 2.2s + number ≤2.9s + next 2.8s + pad 1s ≈ 9s, plus cushion).
POST_THIRD_HOLD_SECONDS = 12.0
DRAW_COMPLETE_SECONDS = REVEAL_INTERVAL_SECONDS * 3 + POST_THIRD_HOLD_SECONDS


class LottoError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def prize_math(stake: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return pool, 1st, 2nd, 3rd, and system fee (4%). Residual cents go to system."""
    stake = Decimal(stake).quantize(MONEY)
    pool = (stake * CAPACITY).quantize(MONEY)
    first = (pool * FIRST_RATE).quantize(MONEY, rounding=ROUND_DOWN)
    second = (pool * SECOND_RATE).quantize(MONEY, rounding=ROUND_DOWN)
    third = (pool * THIRD_RATE).quantize(MONEY, rounding=ROUND_DOWN)
    system = (pool - first - second - third).quantize(MONEY)
    return pool, first, second, third, system


def compute_lotto_house_fee(
    *,
    pool: Decimal,
    prize_total: Decimal = Decimal("0"),
    bot_stake_total: Decimal = Decimal("0"),
    real_stake_total: Decimal | None = None,
) -> Decimal:
    """Real-only share of the structural 4% reserve (ROUND_DOWN to 0.01).

    Prize ladder and wallet credits stay 60/24/12 of the **full** pool; fee
    accounting uses only the real-funded share of the 4% cut:

        structural_4pct = pool × 0.04
        house_fee       = max(0, structural_4pct − bot_stakes × 0.04)
                        = max(0, real_stakes × 0.04)

    Examples (pool 250):

        real 80 + bot 170 → 10.00 − 6.80 = 3.20
        real 130 + bot 120 → 10.00 − 4.80 = 5.20
        all-real (no bot)  → 10.00

    ``prize_total`` is ignored (kept for call-site compatibility). Persisted for
    analytics / display and mirrored onto ``reserve_amount`` at settle.
    Separate from ``system_gain`` (real P&L minus bot×0.04); do not equate them.
    """
    _ = prize_total
    if real_stake_total is not None:
        real_q = max(Decimal("0.00"), Decimal(real_stake_total).quantize(MONEY))
    else:
        pool_q = Decimal(pool).quantize(MONEY)
        bot_q = max(Decimal("0.00"), Decimal(bot_stake_total).quantize(MONEY))
        real_q = max(Decimal("0.00"), (pool_q - bot_q).quantize(MONEY))
    return max(
        Decimal("0.00"),
        (real_q * SYSTEM_RATE).quantize(MONEY, rounding=ROUND_DOWN),
    )


def compute_lotto_round_system_gain(
    real_stake_total: Decimal,
    real_prizes: Decimal = Decimal("0"),
    *,
    bot_stake_total: Decimal | None = None,
    bot_prizes: Decimal | None = None,
    bot_won: bool | None = None,
    house_cut: Decimal | None = None,
    pool: Decimal | None = None,
) -> Decimal:
    """Admin-recognized Lotto P&L for one round (bot-aware GGR).

    Prize ladder and wallet credits stay 60/24/12 of the **full** pool. Admin
    ``system_gain`` is real-player net cashflow minus the bot stake share of the
    structural 4% reserve (so bot fill does not inflate GGR):

        system_gain = (real_stakes − real_prizes) − (bot_stakes × 0.04)

    With no bots (``bot_stakes = 0``) this is classic GGR ``real_stakes −
    real_prizes`` (on a full-payout ladder that residual includes the 4% house
    cut — do **not** also subtract ``pool × 0.04``). May be negative when reals
    win large prizes. Separate from ``house_fee`` / ``reserve_amount``.

    ``bot_prizes`` / ``bot_won`` / ``house_cut`` / ``pool`` are ignored extras
    kept for call-site compatibility.

    Examples:

        bot 160, real 90, real_prizes 0  → 90 − 6.40 = 83.60
        bot 170, real 80, real_prizes 60 → 20 − 6.80 = 13.20
        no bots, pool 250, prizes 240    → 10.00
    """
    _ = (bot_prizes, bot_won, house_cut, pool)
    real_q = max(Decimal("0.00"), Decimal(real_stake_total).quantize(MONEY))
    prizes_q = max(Decimal("0.00"), Decimal(real_prizes).quantize(MONEY))
    bot_q = max(
        Decimal("0.00"),
        Decimal(bot_stake_total or 0).quantize(MONEY),
    )
    bot_fee = (bot_q * SYSTEM_RATE).quantize(MONEY, rounding=ROUND_DOWN)
    return (real_q - prizes_q - bot_fee).quantize(MONEY)


def parse_stake(raw: object) -> Decimal:
    try:
        stake = Decimal(str(raw)).quantize(MONEY)
    except Exception as exc:
        raise LottoError("Invalid room stake") from exc
    if stake not in STAKES:
        raise LottoError("Room stake must be 10, 25, 50, or 100 ETB")
    return stake


def validate_numbers(values: list[int]) -> list[int]:
    if not values or len(values) > CAPACITY:
        raise LottoError(f"Choose between 1 and {CAPACITY} numbers")
    try:
        numbers = [int(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise LottoError("Numbers must be integers") from exc
    if len(set(numbers)) != len(numbers):
        raise LottoError("Duplicate numbers are not allowed")
    if any(number < 1 or number > CAPACITY for number in numbers):
        raise LottoError(f"Numbers must be between 1 and {CAPACITY}")
    return sorted(numbers)


def _new_round(stake: Decimal) -> LottoRound:
    pool, first, second, third, system = prize_math(stake)
    token = uuid4().hex[:10].upper()
    return LottoRound(
        room_stake=stake,
        round_code=f"L{int(stake):03d}-{token}",
        status="open",
        capacity=CAPACITY,
        total_pool=pool,
        first_prize=first,
        second_prize=second,
        third_prize=third,
        reserve_amount=system,
    )


def current_round(db: Session, stake: Decimal, *, lock: bool = False) -> LottoRound:
    query = (
        db.query(LottoRound)
        .filter(
            LottoRound.room_stake == stake,
            LottoRound.status.in_(ACTIVE_STATUSES),
        )
        .order_by(LottoRound.created_at.desc())
    )
    if lock:
        query = query.with_for_update()
    round_ = query.first()
    if round_ is None:
        try:
            # A savepoint preserves any outer user/round locks if another
            # worker wins the lazy room-creation race.
            with db.begin_nested():
                round_ = _new_round(stake)
                db.add(round_)
                db.flush()
        except IntegrityError:
            round_ = (
                db.query(LottoRound)
                .filter(
                    LottoRound.room_stake == stake,
                    LottoRound.status.in_(ACTIVE_STATUSES),
                )
                .order_by(LottoRound.created_at.desc())
                .first()
            )
            if round_ is None:
                raise
    return round_


def ensure_rooms(db: Session) -> None:
    for stake in STAKES:
        current_round(db, stake)
    db.commit()


def _human_display_name(user: User) -> str:
    return user.first_name or user.username or f"Player {str(user.id)[:6]}"


def _resolve_display_name(
    reservation: LottoReservation, user: User, *, round_code: str
) -> str:
    """Prefer persisted public label; fall back for legacy rows."""
    from app.bingo.dummy_names import pick_dummy_name

    if reservation.display_name:
        return reservation.display_name
    if user.is_bot:
        return pick_dummy_name(round_code, f"{reservation.number}")
    return _human_display_name(user)


def _owner_payload(reservation: LottoReservation, user: User, *, round_code: str) -> dict:
    from app.bingo.dummy_names import label5

    name = _resolve_display_name(reservation, user, round_code=round_code)
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "P"
    return {
        "number": reservation.number,
        "user_id": str(reservation.user_id),
        "display_name": name,
        "label5": label5(name),
        "initials": initials,
    }


def _allocate_reservation_names(
    db: Session,
    *,
    round_: LottoRound,
    user: User,
    numbers: list[int],
) -> dict[int, str]:
    """Assign per-number public labels for a reservation batch.

    Bot numbers each get a distinct dummy from the shared pool (no reuse of
    names already on this round). Humans get their real first_name (same on
    every number they hold).
    """
    from app.bingo.dummy_names import pick_unused_dummy

    if not user.is_bot:
        name = _human_display_name(user)
        return {number: name for number in numbers}

    used = {
        row.display_name
        for row in db.query(LottoReservation.display_name)
        .filter(
            LottoReservation.round_id == round_.id,
            LottoReservation.display_name.isnot(None),
        )
        .all()
        if row.display_name
    }
    assigned: dict[int, str] = {}
    for number in numbers:
        name = pick_unused_dummy(round_.round_code, number, used)
        used.add(name)
        assigned[number] = name
    return assigned


def draw_winning_numbers(
    reservations: dict[int, LottoReservation],
    *,
    count: int = 3,
) -> list[int]:
    """Sample ``count`` winning numbers with unique ``user_id`` when possible.

    Numbers stay unique. If a user's second number would win, skip it and take
    another user's number. When fewer than ``count`` distinct holders exist,
    fall back to unique numbers only (monopoly room edge case).
    """
    rng = secrets.SystemRandom()
    population = list(reservations.keys())
    if len(population) < count:
        raise RuntimeError("Not enough reserved numbers to draw winners")

    holders = {reservations[n].user_id for n in population}
    if len(holders) < count:
        return rng.sample(population, count)

    ordered = list(population)
    rng.shuffle(ordered)
    picked: list[int] = []
    used_users: set[UUID] = set()
    for number in ordered:
        user_id = reservations[number].user_id
        if user_id in used_users:
            continue
        picked.append(number)
        used_users.add(user_id)
        if len(picked) == count:
            return picked
    # Distinct holders existed but shuffle path somehow fell short — resample.
    return rng.sample(population, count)


def serialize_round(db: Session, round_: LottoRound, now: datetime | None = None) -> dict:
    now = now or utcnow()
    reservations = (
        db.query(LottoReservation, User)
        .join(User, User.id == LottoReservation.user_id)
        .filter(LottoReservation.round_id == round_.id)
        .order_by(LottoReservation.number)
        .all()
    )
    winners = (
        db.query(LottoWinner, User)
        .join(User, User.id == LottoWinner.user_id)
        .filter(LottoWinner.round_id == round_.id)
        .order_by(LottoWinner.rank)
        .all()
    )
    visible_count = 0
    drawing_started = _aware(round_.drawing_started_at)
    if round_.status == "completed":
        visible_count = 3
    elif round_.status == "drawing" and drawing_started:
        elapsed = max(0.0, (now - drawing_started).total_seconds())
        visible_count = min(3, int(elapsed // REVEAL_INTERVAL_SECONDS) + 1)

    by_number = {item.number: (item, user) for item, user in reservations}

    return {
        "id": str(round_.id),
        "round_code": round_.round_code,
        "stake": str(round_.room_stake),
        "status": round_.status,
        "capacity": round_.capacity,
        "occupied": len(reservations),
        "total_pool": str(round_.total_pool),
        "first_prize": str(round_.first_prize),
        "second_prize": str(round_.second_prize),
        "third_prize": str(round_.third_prize),
        "reserve_amount": str(round_.reserve_amount),
        "countdown_started_at": (
            _aware(round_.countdown_started_at).isoformat()
            if round_.countdown_started_at
            else None
        ),
        "draw_scheduled_at": (
            _aware(round_.draw_scheduled_at).isoformat()
            if round_.draw_scheduled_at
            else None
        ),
        # Alias for clients: end of the 60s pre-draw wait (= draw_scheduled_at).
        "pre_draw_ends_at": (
            _aware(round_.draw_scheduled_at).isoformat()
            if round_.draw_scheduled_at
            else None
        ),
        "drawing_started_at": (
            drawing_started.isoformat() if drawing_started else None
        ),
        "completed_at": (
            _aware(round_.completed_at).isoformat() if round_.completed_at else None
        ),
        "reservations": [
            _owner_payload(item, user, round_code=round_.round_code)
            for item, user in reservations
        ],
        "winners": [
            {
                "rank": winner.rank,
                "number": winner.number,
                "user_id": str(winner.user_id),
                "display_name": _resolve_display_name(
                    by_number[winner.number][0],
                    by_number[winner.number][1],
                    round_code=round_.round_code,
                ),
                "prize": str(winner.prize),
                "revealed_at": (
                    drawing_started
                    + timedelta(seconds=(winner.rank - 1) * REVEAL_INTERVAL_SECONDS)
                ).isoformat()
                if drawing_started
                else None,
            }
            for winner, _user in winners[:visible_count]
            if winner.number in by_number
        ],
    }


def snapshot(db: Session) -> dict:
    ensure_rooms(db)
    rounds = [current_round(db, stake) for stake in STAKES]
    return {
        "type": "snapshot",
        "server_time": utcnow().isoformat(),
        "rooms": [serialize_round(db, item) for item in rounds],
    }


def _reservation_response(
    db: Session,
    request: LottoReservationRequest,
    balance: Decimal,
    *,
    replayed: bool,
) -> dict:
    round_ = db.query(LottoRound).filter(LottoRound.id == request.round_id).one()
    numbers = [int(value) for value in request.numbers_csv.split(",") if value]
    return {
        "request_id": str(request.request_id),
        "round": serialize_round(db, round_),
        "numbers": numbers,
        "charged_amount": str(request.charged_amount),
        "balance": str(balance),
        "replayed": replayed,
    }


def reserve(
    db: Session,
    *,
    user_id: UUID,
    raw_stake: object,
    raw_numbers: list[int],
    request_id: UUID,
) -> dict:
    stake = parse_stake(raw_stake)
    numbers = validate_numbers(raw_numbers)
    numbers_csv = ",".join(map(str, numbers))
    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .with_for_update()
            .one_or_none()
        )
        if user is None:
            raise LottoError("User not found", 404)

        existing = (
            db.query(LottoReservationRequest)
            .filter(
                LottoReservationRequest.user_id == user_id,
                LottoReservationRequest.request_id == request_id,
            )
            .first()
        )
        if existing:
            round_ = db.query(LottoRound).filter(LottoRound.id == existing.round_id).one()
            if existing.numbers_csv != numbers_csv or Decimal(round_.room_stake) != stake:
                raise LottoError("Request id was already used for different data", 409)
            return _reservation_response(db, existing, user.balance, replayed=True)

        round_ = current_round(db, stake, lock=True)
        if round_.status != "open":
            raise LottoError("This round is no longer open", 409)

        occupied = {
            value[0]
            for value in db.query(LottoReservation.number)
            .filter(
                LottoReservation.round_id == round_.id,
                LottoReservation.number.in_(numbers),
            )
            .all()
        }
        if occupied:
            joined = ", ".join(map(str, sorted(occupied)))
            raise LottoError(f"Number(s) already reserved: {joined}", 409)

        occupied_count = (
            db.query(func.count(LottoReservation.id))
            .filter(LottoReservation.round_id == round_.id)
            .scalar()
            or 0
        )
        if occupied_count + len(numbers) > round_.capacity:
            raise LottoError("Not enough open positions", 409)

        charge = (stake * len(numbers)).quantize(MONEY)
        if user.balance < charge:
            raise LottoError("Insufficient balance", 409)

        transaction = credit_wallet(
            db,
            user,
            amount=-charge,
            transaction_type="LOTTO_RESERVE",
            description=f"Lotto {round_.round_code}: {numbers_csv}",
            reference_type="LOTTO_REQUEST",
            reference_id=request_id,
        )
        db.flush()
        request = LottoReservationRequest(
            user_id=user.id,
            round_id=round_.id,
            request_id=request_id,
            numbers_csv=numbers_csv,
            charged_amount=charge,
            wallet_transaction_id=transaction.id,
        )
        db.add(request)
        labels = _allocate_reservation_names(
            db, round_=round_, user=user, numbers=numbers
        )
        db.add_all(
            [
                LottoReservation(
                    round_id=round_.id,
                    user_id=user.id,
                    request_id=request_id,
                    number=number,
                    stake=stake,
                    display_name=labels[number],
                )
                for number in numbers
            ]
        )
        db.flush()

        if occupied_count + len(numbers) == round_.capacity:
            now = utcnow()
            round_.status = "countdown"
            round_.countdown_started_at = now
            round_.draw_scheduled_at = now + timedelta(seconds=COUNTDOWN_SECONDS)
            round_.version += 1

        db.commit()
        return _reservation_response(db, request, user.balance, replayed=False)
    except IntegrityError as exc:
        db.rollback()
        # Concurrent duplicate submit with the same request_id: the first
        # writer won. Treat as idempotent replay instead of a false conflict.
        existing = (
            db.query(LottoReservationRequest)
            .filter(
                LottoReservationRequest.user_id == user_id,
                LottoReservationRequest.request_id == request_id,
            )
            .first()
        )
        if existing is not None:
            user = db.query(User).filter(User.id == user_id).one_or_none()
            if user is None:
                raise LottoError("User not found", 404) from exc
            if existing.numbers_csv != numbers_csv:
                raise LottoError(
                    "Request id was already used for different data", 409
                ) from exc
            return _reservation_response(db, existing, user.balance, replayed=True)
        raise LottoError(
            "One or more numbers were reserved by another player", 409
        ) from exc
    except Exception:
        db.rollback()
        raise


def release_bot_numbers(
    db: Session,
    *,
    round_id: UUID,
    bot_user_id: UUID,
    numbers: list[int] | None = None,
) -> dict:
    """Refund and free bot-held numbers on an **open** round only.

    Used by the house bot under real-player pressure or when disabled. Players
    have no public release path — this is internal/bot-only.
    """

    try:
        round_ = (
            db.query(LottoRound)
            .filter(LottoRound.id == round_id)
            .with_for_update()
            .one_or_none()
        )
        if round_ is None:
            raise LottoError("Round not found", 404)
        if round_.status != "open":
            raise LottoError("Can only release bot numbers while the room is open", 409)

        bot = (
            db.query(User)
            .filter(User.id == bot_user_id)
            .with_for_update()
            .one_or_none()
        )
        if bot is None or not bot.is_bot:
            raise LottoError("Bot user not found", 404)

        query = db.query(LottoReservation).filter(
            LottoReservation.round_id == round_.id,
            LottoReservation.user_id == bot_user_id,
        )
        if numbers is not None:
            validated = validate_numbers(numbers) if numbers else []
            if not validated:
                return {
                    "released": [],
                    "refunded": "0.00",
                    "balance": str(bot.balance),
                    "round": serialize_round(db, round_),
                }
            query = query.filter(LottoReservation.number.in_(validated))

        held = query.order_by(LottoReservation.number).all()
        if not held:
            return {
                "released": [],
                "refunded": "0.00",
                "balance": str(bot.balance),
                "round": serialize_round(db, round_),
            }

        released = [row.number for row in held]
        refund = (Decimal(round_.room_stake) * len(released)).quantize(MONEY)
        credit_wallet(
            db,
            bot,
            amount=refund,
            transaction_type="LOTTO_BOT_RELEASE",
            description=f"Lotto bot release {round_.round_code}: {','.join(map(str, released))}",
            reference_type="LOTTO_ROUND",
            reference_id=round_.id,
        )
        for row in held:
            db.delete(row)
        # Drop orphaned reservation requests that no longer have numbers.
        # Keep it simple: leave request rows; settlement only cares about reservations.
        round_.version += 1
        db.commit()
        db.refresh(bot)
        return {
            "released": released,
            "refunded": str(refund),
            "balance": str(bot.balance),
            "round": serialize_round(db, round_),
        }
    except LottoError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def settle_due_round(db: Session, round_id: UUID) -> bool:
    """Persist all winners and credits atomically. Safe to call repeatedly."""
    try:
        round_ = (
            db.query(LottoRound)
            .filter(LottoRound.id == round_id)
            .with_for_update()
            .one_or_none()
        )
        if round_ is None:
            return False
        existing = (
            db.query(LottoWinner)
            .filter(LottoWinner.round_id == round_.id)
            .order_by(LottoWinner.rank)
            .all()
        )
        if existing:
            if round_.status == "countdown":
                round_.status = "drawing"
                round_.drawing_started_at = round_.drawing_started_at or utcnow()
                db.commit()
            return False
        if round_.status != "countdown":
            return False
        scheduled = _aware(round_.draw_scheduled_at)
        if scheduled and scheduled > utcnow():
            return False

        reservations = {
            item.number: item
            for item in db.query(LottoReservation)
            .filter(LottoReservation.round_id == round_.id)
            .all()
        }
        if len(reservations) != round_.capacity:
            raise RuntimeError("Cannot draw an incomplete Lotto round")

        # Distinct users across ranks when possible; numbers always unique.
        winning_numbers = draw_winning_numbers(reservations, count=3)
        prizes = (round_.first_prize, round_.second_prize, round_.third_prize)
        users: dict[UUID, User] = {}
        for reservation in reservations.values():
            users.setdefault(reservation.user_id, None)  # type: ignore[arg-type]
        locked_users = (
            db.query(User)
            .filter(User.id.in_(list(users)))
            .order_by(User.id)
            .with_for_update()
            .all()
        )
        users = {user.id: user for user in locked_users}

        real_stake_total = Decimal("0.00")
        bot_stake_total = Decimal("0.00")
        for reservation in reservations.values():
            holder = users[reservation.user_id]
            amount = Decimal(reservation.stake).quantize(MONEY)
            if holder.is_bot:
                bot_stake_total += amount
            else:
                real_stake_total += amount
        real_stake_total = real_stake_total.quantize(MONEY)
        bot_stake_total = bot_stake_total.quantize(MONEY)

        round_.status = "drawing"
        round_.drawing_started_at = utcnow()
        round_.version += 1
        winner_is_bot: list[bool] = []
        bot_prizes = Decimal("0.00")
        for rank, (number, prize) in enumerate(zip(winning_numbers, prizes), start=1):
            reservation = reservations[number]
            user = users[reservation.user_id]
            is_bot = bool(user.is_bot)
            winner_is_bot.append(is_bot)
            prize_q = Decimal(prize).quantize(MONEY)
            if is_bot:
                bot_prizes += prize_q
            tx = credit_wallet(
                db,
                user,
                amount=prize,
                transaction_type="LOTTO_PAYOUT",
                description=f"Lotto {round_.round_code} rank {rank}, number {number}",
                reference_type=f"LOTTO_WIN_{rank}",
                reference_id=round_.id,
            )
            db.flush()
            db.add(
                LottoWinner(
                    round_id=round_.id,
                    rank=rank,
                    number=number,
                    user_id=user.id,
                    prize=prize,
                    payout_transaction_id=tx.id,
                )
            )
        bot_prizes = bot_prizes.quantize(MONEY)
        prize_total = (
            Decimal(round_.first_prize)
            + Decimal(round_.second_prize)
            + Decimal(round_.third_prize)
        ).quantize(MONEY)
        house_fee = compute_lotto_house_fee(
            pool=Decimal(round_.total_pool),
            prize_total=prize_total,
            bot_stake_total=bot_stake_total,
            real_stake_total=real_stake_total,
        )
        # All prize ranks bot → informational flag.
        # system_gain = (real_stakes − real_prizes) − (bot_stakes × 0.04)
        # (separate from house_fee / reserve_amount = max(0, real × 0.04)).
        bot_won = bool(winner_is_bot) and all(winner_is_bot)
        real_prizes = (prize_total - bot_prizes).quantize(MONEY)
        round_.bot_won = bot_won
        round_.real_stake_total = real_stake_total
        round_.bot_stake_total = bot_stake_total
        round_.bot_prizes = bot_prizes
        round_.house_fee = house_fee
        # Display "system" cut matches real-only 4% when bots filled the room
        # (creation-time residual is always 0.04×pool).
        round_.reserve_amount = house_fee
        round_.system_gain = compute_lotto_round_system_gain(
            real_stake_total,
            real_prizes,
            bot_stake_total=bot_stake_total,
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def complete_due_round(db: Session, round_id: UUID) -> bool:
    try:
        round_ = (
            db.query(LottoRound)
            .filter(LottoRound.id == round_id)
            .with_for_update()
            .one_or_none()
        )
        if round_ is None or round_.status != "drawing":
            return False
        started = _aware(round_.drawing_started_at)
        if not started or (utcnow() - started).total_seconds() < DRAW_COMPLETE_SECONDS:
            return False
        if (
            db.query(func.count(LottoWinner.id))
            .filter(LottoWinner.round_id == round_.id)
            .scalar()
            != 3
        ):
            raise RuntimeError("Lotto settlement is incomplete")
        round_.status = "completed"
        round_.completed_at = utcnow()
        round_.version += 1
        db.flush()
        db.add(_new_round(Decimal(round_.room_stake)))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def recoverable_rounds(db: Session) -> list[LottoRound]:
    return (
        db.query(LottoRound)
        .filter(LottoRound.status.in_(("countdown", "drawing")))
        .order_by(LottoRound.created_at)
        .all()
    )


def history(db: Session, user_id: UUID, limit: int, offset: int) -> dict:
    participation = (
        db.query(LottoReservation.round_id)
        .join(LottoRound, LottoRound.id == LottoReservation.round_id)
        .filter(
            LottoReservation.user_id == user_id,
            LottoRound.status == "completed",
        )
        .group_by(LottoReservation.round_id, LottoRound.completed_at)
    )
    total = participation.count()
    ids = [
        row[0]
        for row in participation
        .order_by(LottoRound.completed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    ]
    rounds = {
        item.id: item
        for item in db.query(LottoRound).filter(LottoRound.id.in_(ids)).all()
    }
    reservations = (
        db.query(LottoReservation)
        .filter(
            LottoReservation.user_id == user_id,
            LottoReservation.round_id.in_(ids),
        )
        .all()
        if ids
        else []
    )
    winners = (
        db.query(LottoWinner)
        .filter(LottoWinner.user_id == user_id, LottoWinner.round_id.in_(ids))
        .all()
        if ids
        else []
    )
    owned: dict[UUID, list[int]] = {}
    won: dict[UUID, list[LottoWinner]] = {}
    for item in reservations:
        owned.setdefault(item.round_id, []).append(item.number)
    for item in winners:
        won.setdefault(item.round_id, []).append(item)

    items = []
    for round_id in ids:
        round_ = rounds[round_id]
        numbers = sorted(owned.get(round_id, []))
        paid = (Decimal(round_.room_stake) * len(numbers)).quantize(MONEY)
        round_winners = sorted(won.get(round_id, []), key=lambda item: item.rank)
        prize = sum((Decimal(item.prize) for item in round_winners), Decimal("0.00"))
        items.append(
            {
                "round_id": str(round_.id),
                "round_code": round_.round_code,
                "stake": str(round_.room_stake),
                "numbers": numbers,
                "total_paid": str(paid),
                "winners": [
                    {
                        "rank": item.rank,
                        "number": item.number,
                        "prize": str(item.prize),
                    }
                    for item in round_winners
                ],
                "total_prize": str(prize),
                "net": str(prize - paid),
                "completed_at": _aware(round_.completed_at).isoformat(),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
