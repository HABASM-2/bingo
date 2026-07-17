"""Transactional, server-authoritative Plinko settlement."""

from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.plinko_game import PlinkoPlay
from app.models.user import User
from app.services.wallet_service import credit_wallet
from app.plinko.config import (
    ALLOWED_RISKS,
    ALLOWED_ROWS,
    MAX_STAKE,
    MIN_STAKE,
    MULTIPLIER_TABLES,
)

BET_TX_TYPE = "PLINKO_BET"
PAYOUT_TX_TYPE = "PLINKO_PAYOUT"
MONEY = Decimal("0.01")


def compute_payout(stake: Decimal, multiplier: Decimal) -> Decimal:
    """Paid credit = stake * multiplier, rounded once to cents (half-up)."""
    return (stake * multiplier).quantize(MONEY, rounding=ROUND_HALF_UP)


def parse_stake(raw: object) -> Decimal:
    try:
        stake = Decimal(str(raw)).quantize(MONEY)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid stake") from exc
    if not stake.is_finite() or stake < 0:
        raise ValueError("Stake must be zero or greater")
    if stake != 0 and not MIN_STAKE <= stake <= MAX_STAKE:
        raise ValueError(f"Paid stake must be between {MIN_STAKE} and {MAX_STAKE} ETB")
    return stake


def validate_board(risk: str, rows: int) -> None:
    if risk not in ALLOWED_RISKS:
        raise ValueError("Risk must be low, medium, or high")
    if rows not in ALLOWED_ROWS:
        raise ValueError(f"Rows must be one of {', '.join(map(str, ALLOWED_ROWS))}")


def choose_slot(rows: int) -> int:
    """A binomial Galton-board result using cryptographic random bits."""
    return sum(secrets.randbits(1) for _ in range(rows))


def _serialize(play: PlinkoPlay, balance: Decimal | None) -> dict:
    return {
        "play_id": str(play.id),
        "slot_index": play.slot_index,
        "multiplier": str(play.multiplier),
        "stake": str(play.stake),
        "payout": str(play.payout),
        "net": str(play.net_result),
        "is_demo": play.is_demo,
        "balance": str(balance) if balance is not None else None,
        "risk": play.risk,
        "rows": play.rows,
        "created_at": play.created_at.isoformat() if play.created_at else None,
    }


def play(
    db: Session,
    *,
    user_id: UUID,
    play_id: UUID,
    raw_stake: object,
    risk: str,
    rows: int,
) -> dict:
    stake = parse_stake(raw_stake)
    validate_board(risk, rows)

    # Lock for every play, including demo, so duplicate idempotency keys cannot
    # race each other into the primary-key constraint.
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .one_or_none()
    )
    if user is None:
        raise ValueError("User not found")
    existing = db.query(PlinkoPlay).filter(PlinkoPlay.id == play_id).first()
    if existing is not None:
        if existing.user_id != user_id:
            raise ValueError("Invalid play id")
        return _serialize(existing, user.balance if not existing.is_demo else None)

    slot = choose_slot(rows)
    multiplier = MULTIPLIER_TABLES[risk][rows][slot]
    is_demo = stake == 0
    # No service fee / rake: credit is exactly stake * multiplier (demo: no wallet).
    payout = Decimal("0.00") if is_demo else compute_payout(stake, multiplier)
    net = Decimal("0.00") if is_demo else payout - stake

    balance: Decimal | None = None
    try:
        if not is_demo:
            if user.balance < stake:
                raise ValueError("Insufficient balance")
            credit_wallet(
                db,
                user,
                amount=-stake,
                transaction_type=BET_TX_TYPE,
                description=f"Plinko stake ({play_id}) - {stake} ETB",
                reference_type="PLINKO",
                reference_id=play_id,
            )
            if payout > 0:
                credit_wallet(
                    db,
                    user,
                    amount=payout,
                    transaction_type=PAYOUT_TX_TYPE,
                    description=f"Plinko payout ({play_id}) - {payout} ETB",
                    reference_type="PLINKO",
                    reference_id=play_id,
                )
            balance = user.balance

        record = PlinkoPlay(
            id=play_id,
            user_id=user_id,
            stake=stake,
            risk=risk,
            rows=rows,
            slot_index=slot,
            multiplier=multiplier,
            payout=payout,
            net_result=net,
            is_demo=is_demo,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return _serialize(record, balance)
    except Exception:
        db.rollback()
        raise


def history(db: Session, user_id: UUID, limit: int, offset: int) -> dict:
    query = db.query(PlinkoPlay).filter(PlinkoPlay.user_id == user_id)
    total, paid, demo = (
        db.query(
            func.count(PlinkoPlay.id),
            func.count(PlinkoPlay.id).filter(PlinkoPlay.is_demo.is_(False)),
            func.count(PlinkoPlay.id).filter(PlinkoPlay.is_demo.is_(True)),
        )
        .filter(PlinkoPlay.user_id == user_id)
        .one()
    )
    records = (
        query.order_by(PlinkoPlay.created_at.desc(), PlinkoPlay.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize(item, None) for item in records],
        "total": int(total or 0),
        "paid_count": int(paid or 0),
        "demo_count": int(demo or 0),
    }
