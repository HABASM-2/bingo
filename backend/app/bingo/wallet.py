"""Bridge between the async Bingo engine and the synchronous SQLAlchemy
wallet.

The rest of the app talks to Postgres synchronously (``SessionLocal`` +
``wallet_service``), so these helpers do their DB work inside a plain
session and are invoked from the async game loop via ``asyncio.to_thread``.
Every balance change is mirrored into ``wallet_transactions`` so staking a
board and winning a derash show up in the same ledger as deposits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.db.database import SessionLocal
from app.models.bingo_game import BingoGame, BingoGameResult
from app.models.user import User
from app.services.wallet_service import credit_wallet

STAKE_TX_TYPE = "BINGO_STAKE"
WIN_TX_TYPE = "BINGO_WIN"


def _load_user(db, user_id: str) -> User | None:
    try:
        return db.query(User).filter(User.id == UUID(user_id)).first()
    except (ValueError, TypeError):
        return None


def charge_stakes(
    charges: dict[str, Decimal],
    game_id: str,
) -> dict[str, str]:
    """Debit each player's stake for the round.

    ``charges`` maps user_id -> total amount owed (board_price * boards).
    Players who can afford it are debited; those who can't are skipped.
    Returns user_id -> resulting balance (as string) for every player that
    was successfully charged, so the caller can drop unpaid players from the
    round and refresh their displayed balance.
    """

    if not charges:
        return {}

    paid: dict[str, str] = {}
    db = SessionLocal()

    try:
        for user_id, amount in charges.items():
            if amount <= 0:
                continue

            user = _load_user(db, user_id)

            if user is None or user.balance < amount:
                continue

            credit_wallet(
                db,
                user,
                amount=-amount,
                transaction_type=STAKE_TX_TYPE,
                description=f"Bingo stake ({game_id}) - {amount} ETB",
                reference_type="BINGO",
            )

            paid[user_id] = str(user.balance)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return paid


def award_prize(user_id: str, amount: Decimal, game_id: str) -> str | None:
    """Credit the winner's derash. Returns the new balance (string) or None."""

    if amount <= 0:
        return None

    db = SessionLocal()

    try:
        user = _load_user(db, user_id)

        if user is None:
            return None

        credit_wallet(
            db,
            user,
            amount=amount,
            transaction_type=WIN_TX_TYPE,
            description=f"Bingo win ({game_id}) - {amount} ETB",
            reference_type="BINGO",
        )

        db.commit()

        return str(user.balance)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def award_prizes(plan: dict[str, Decimal], game_id: str) -> dict[str, str]:
    """Credit several winners in one session (multi-winner / split derash).

    ``plan`` maps user_id -> total prize for that user (already summed across
    however many of their boards won). Returns user_id -> new balance (string)
    for every user that was credited.
    """

    if not plan:
        return {}

    balances: dict[str, str] = {}
    db = SessionLocal()

    try:
        for user_id, amount in plan.items():
            if amount <= 0:
                continue

            user = _load_user(db, user_id)

            if user is None:
                continue

            credit_wallet(
                db,
                user,
                amount=amount,
                transaction_type=WIN_TX_TYPE,
                description=f"Bingo win ({game_id}) - {amount} ETB",
                reference_type="BINGO",
            )

            balances[user_id] = str(user.balance)

        db.commit()

        return balances
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_balance(user_id: str) -> str:
    db = SessionLocal()

    try:
        user = _load_user(db, user_id)

        return str(user.balance) if user is not None else "0"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# History persistence (BingoGame / BingoGameResult)
# ---------------------------------------------------------------------------

def record_round_start(
    game_code: str,
    room_id: str,
    board_price: Decimal,
    participants: dict[str, int],
    derash: Decimal,
) -> None:
    """Persist a round the moment it starts.

    ``participants`` maps user_id -> number of paid boards staked. One row is
    written per paying user (their stake = board_price * boards) plus the parent
    ``BingoGame`` row (status ``in_progress``). Recording is best-effort: a
    history write must never break live gameplay, so failures are swallowed.
    """

    if not participants:
        return

    total_boards = sum(participants.values())

    if total_boards <= 0:
        return

    db = SessionLocal()

    try:
        # Idempotent: never double-insert a round if start is retried.
        existing = (
            db.query(BingoGame)
            .filter(BingoGame.game_code == game_code)
            .first()
        )

        if existing is not None:
            return

        game = BingoGame(
            game_code=game_code,
            room_id=room_id,
            status="in_progress",
            board_price=board_price,
            total_boards=total_boards,
            total_players=len(participants),
            derash=derash,
        )
        db.add(game)
        db.flush()

        for user_id, boards in participants.items():
            try:
                uid = UUID(user_id)
            except (ValueError, TypeError):
                continue

            db.add(
                BingoGameResult(
                    game_id=game.id,
                    user_id=uid,
                    boards_count=boards,
                    stake_amount=board_price * boards,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def record_round_finish(
    game_code: str,
    winners: dict[str, Decimal],
    winning_pattern: str | None,
    winner_count: int,
) -> None:
    """Mark a round finished and stamp winners/amounts onto their result rows.

    ``winners`` maps user_id -> total prize credited to that user. Best-effort.
    """

    db = SessionLocal()

    try:
        game = (
            db.query(BingoGame)
            .filter(BingoGame.game_code == game_code)
            .first()
        )

        if game is None:
            return

        game.status = "finished"
        game.winning_pattern = winning_pattern
        game.winner_count = winner_count
        game.finished_at = datetime.now(timezone.utc)

        for user_id, amount in winners.items():
            try:
                uid = UUID(user_id)
            except (ValueError, TypeError):
                continue

            result = (
                db.query(BingoGameResult)
                .filter(
                    BingoGameResult.game_id == game.id,
                    BingoGameResult.user_id == uid,
                )
                .first()
            )

            if result is not None:
                result.is_winner = True
                result.amount_won = amount

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def record_round_abandoned(game_code: str) -> None:
    """Close out a round that ended with no winner (drew out or abandoned)."""

    db = SessionLocal()

    try:
        game = (
            db.query(BingoGame)
            .filter(BingoGame.game_code == game_code)
            .first()
        )

        if game is None or game.status == "finished":
            return

        game.status = "finished"
        game.finished_at = datetime.now(timezone.utc)

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_user_history(user_id: str, limit: int = 30) -> list[dict]:
    """Recent finished/played rounds for a user, newest first."""

    try:
        uid = UUID(user_id)
    except (ValueError, TypeError):
        return []

    db = SessionLocal()

    try:
        rows = (
            db.query(BingoGameResult, BingoGame)
            .join(BingoGame, BingoGameResult.game_id == BingoGame.id)
            .filter(BingoGameResult.user_id == uid)
            .order_by(BingoGame.created_at.desc())
            .limit(limit)
            .all()
        )

        history: list[dict] = []

        for result, game in rows:
            history.append(
                {
                    "game_id": game.game_code,
                    "status": game.status,
                    "total_boards": game.total_boards,
                    "total_players": game.total_players,
                    "derash": str(game.derash),
                    "boards_count": result.boards_count,
                    "stake": str(result.stake_amount),
                    "is_winner": result.is_winner,
                    "amount_won": str(result.amount_won),
                    "winning_pattern": game.winning_pattern,
                    "created_at": (
                        game.created_at.isoformat()
                        if game.created_at is not None
                        else None
                    ),
                }
            )

        return history
    finally:
        db.close()
