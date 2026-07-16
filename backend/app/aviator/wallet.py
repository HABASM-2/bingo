"""Aviator wallet: bet charges, cash-out credits, round settlement."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.aviator_game import AviatorBet, AviatorRound
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
from app.services.wallet_service import credit_wallet

BET_TX_TYPE = "AVIATOR_BET"
CASHOUT_TX_TYPE = "AVIATOR_CASHOUT"

MIN_STAKE = Decimal("1")
MAX_STAKE = Decimal("500")
PRESET_STAKES = (Decimal("5"), Decimal("10"), Decimal("15"))


def parse_stake(raw) -> Decimal:
    try:
        stake = Decimal(str(raw)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValueError("Invalid stake") from exc
    if stake < MIN_STAKE or stake > MAX_STAKE:
        raise ValueError(f"Stake must be between {MIN_STAKE} and {MAX_STAKE} ETB")
    return stake


def _load_user(db, user_id: str, *, for_update: bool = False) -> User | None:
    try:
        query = db.query(User).filter(User.id == UUID(user_id))
        if for_update:
            query = query.with_for_update()
        return query.first()
    except (ValueError, TypeError):
        return None


def charge_bet(user_id: str, stake: Decimal, round_code: str) -> str:
    db = SessionLocal()
    try:
        user = _load_user(db, user_id, for_update=True)
        if user is None or user.balance < stake:
            raise ValueError("Insufficient balance")
        credit_wallet(
            db,
            user,
            amount=-stake,
            transaction_type=BET_TX_TYPE,
            description=f"Aviator bet ({round_code}) - {stake} ETB",
            reference_type="AVIATOR",
        )
        db.commit()
        return str(user.balance)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def credit_cashout(
    user_id: str,
    amount: Decimal,
    round_code: str,
    bet_id: str,
) -> str:
    if amount <= 0:
        raise ValueError("Invalid payout")
    db = SessionLocal()
    try:
        uid = UUID(user_id)
        reference_id = UUID(bet_id)
        user = _load_user(db, user_id, for_update=True)
        if user is None:
            raise ValueError("User not found")
        existing = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == uid,
                WalletTransaction.transaction_type == CASHOUT_TX_TYPE,
                WalletTransaction.reference_id == reference_id,
            )
            .first()
        )
        if existing is not None:
            return str(user.balance)
        credit_wallet(
            db,
            user,
            amount=amount,
            transaction_type=CASHOUT_TX_TYPE,
            description=f"Aviator cash-out ({round_code}) - {amount} ETB",
            reference_type="AVIATOR",
            reference_id=reference_id,
        )
        db.commit()
        return str(user.balance)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_balance(user_id: str) -> str | None:
    db = SessionLocal()
    try:
        user = _load_user(db, user_id)
        return str(user.balance) if user else None
    finally:
        db.close()


def record_round_finish(
    *,
    round_code: str,
    crash_multiplier: float,
    player_count: int,
    total_stake: Decimal,
    total_payout: Decimal,
    max_payout_mult: Decimal,
    bets: list[dict],
) -> str:
    """Persist round + bets; return DB round UUID string."""
    system_fee = (total_stake - total_payout).quantize(Decimal("0.01"))
    if system_fee < 0:
        system_fee = Decimal("0")

    db = SessionLocal()
    try:
        rnd = AviatorRound(
            round_code=round_code,
            status="finished",
            crash_multiplier=Decimal(str(crash_multiplier)),
            player_count=player_count,
            total_stake=total_stake,
            total_payout=total_payout,
            system_fee=system_fee,
            max_payout_mult=max_payout_mult,
            finished_at=datetime.now(timezone.utc),
        )
        db.add(rnd)
        db.flush()

        for b in bets:
            db.add(
                AviatorBet(
                    round_id=rnd.id,
                    user_id=UUID(b["user_id"]),
                    display_name=b.get("display_name") or "Player",
                    stake=Decimal(str(b["stake"])),
                    cashout_multiplier=(
                        Decimal(str(b["cashout_at"])) if b.get("cashout_at") else None
                    ),
                    amount_won=Decimal(str(b.get("win") or "0")),
                    outcome="won" if b.get("status") == "cashed" else "lost",
                    slot=int(b.get("slot") or 0),
                )
            )
        db.commit()
        return str(rnd.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_user_history(user_id: str, limit: int = 10, offset: int = 0) -> dict:
    db = SessionLocal()
    try:
        uid = UUID(user_id)
        q = (
            db.query(AviatorBet)
            .join(AviatorRound, AviatorRound.id == AviatorBet.round_id)
            .filter(AviatorBet.user_id == uid)
            .order_by(AviatorRound.created_at.desc())
        )
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        wins = (
            db.query(AviatorBet)
            .filter(AviatorBet.user_id == uid, AviatorBet.outcome == "won")
            .count()
        )
        games = []
        for row in rows:
            rnd = db.query(AviatorRound).filter(AviatorRound.id == row.round_id).first()
            games.append(
                {
                    "bet_id": str(row.id),
                    "round_code": rnd.round_code if rnd else "",
                    "stake": str(row.stake),
                    "cashout_multiplier": str(row.cashout_multiplier) if row.cashout_multiplier else None,
                    "amount_won": str(row.amount_won),
                    "outcome": row.outcome,
                    "crash_multiplier": str(rnd.crash_multiplier) if rnd and rnd.crash_multiplier else None,
                    "created_at": rnd.created_at.isoformat() if rnd and rnd.created_at else None,
                }
            )
        return {
            "bets": games,
            "total": total,
            "played": total,
            "wins": wins,
        }
    finally:
        db.close()


def get_top_gainers(limit: int = 20) -> dict:
    """Return players ranked by persisted net gain across all Aviator bets."""
    db = SessionLocal()
    try:
        net_gain = func.sum(AviatorBet.amount_won - AviatorBet.stake)
        rows = (
            db.query(
                AviatorBet.user_id.label("user_id"),
                func.max(AviatorBet.display_name).label("display_name"),
                net_gain.label("net_gain"),
                func.sum(AviatorBet.amount_won).label("total_won"),
                func.count(AviatorBet.id).label("bets_count"),
            )
            .group_by(AviatorBet.user_id)
            .having(net_gain > 0)
            .order_by(net_gain.desc())
            .limit(limit)
            .all()
        )
        return {
            "players": [
                {
                    "rank": index + 1,
                    "user_id": str(row.user_id),
                    "display_name": row.display_name or "Player",
                    "net_gain": str(row.net_gain),
                    "total_won": str(row.total_won),
                    "bets_count": int(row.bets_count),
                }
                for index, row in enumerate(rows)
            ]
        }
    finally:
        db.close()
