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
COUNTDOWN_SECONDS = 3
# Gap between authoritative winner reveals. Must cover frontend anticipation
# (~1s) + dramatic spin (~4.5–6.5s) + readable settle gap (~2–2.8s).
REVEAL_INTERVAL_SECONDS = 11.0
DRAW_COMPLETE_SECONDS = REVEAL_INTERVAL_SECONDS * 3


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


def _owner_payload(reservation: LottoReservation, user: User) -> dict:
    name = user.first_name or user.username or f"Player {str(user.id)[:6]}"
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "P"
    return {
        "number": reservation.number,
        "user_id": str(reservation.user_id),
        "display_name": name,
        "initials": initials,
    }


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
        "drawing_started_at": (
            drawing_started.isoformat() if drawing_started else None
        ),
        "completed_at": (
            _aware(round_.completed_at).isoformat() if round_.completed_at else None
        ),
        "reservations": [_owner_payload(item, user) for item, user in reservations],
        "winners": [
            {
                "rank": winner.rank,
                "number": winner.number,
                "user_id": str(winner.user_id),
                "display_name": (
                    user.first_name or user.username or f"Player {str(user.id)[:6]}"
                ),
                "prize": str(winner.prize),
                "revealed_at": (
                    drawing_started
                    + timedelta(seconds=(winner.rank - 1) * REVEAL_INTERVAL_SECONDS)
                ).isoformat()
                if drawing_started
                else None,
            }
            for winner, user in winners[:visible_count]
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
        db.add_all(
            [
                LottoReservation(
                    round_id=round_.id,
                    user_id=user.id,
                    request_id=request_id,
                    number=number,
                    stake=stake,
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
        raise LottoError("One or more numbers were reserved by another player", 409) from exc
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

        # Winners are drawn only from reserved numbers (all 1..CAPACITY when full).
        winning_numbers = secrets.SystemRandom().sample(list(reservations.keys()), 3)
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

        round_.status = "drawing"
        round_.drawing_started_at = utcnow()
        round_.version += 1
        for rank, (number, prize) in enumerate(zip(winning_numbers, prizes), start=1):
            reservation = reservations[number]
            user = users[reservation.user_id]
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
