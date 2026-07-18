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
BOT_TOPUP_TX_TYPE = "BINGO_BOT_TOPUP"
BOT_SYSTEM_GAIN_TX_TYPE = "BINGO_BOT_SYSTEM_GAIN"


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


def ensure_bot_balance(user_id: str) -> str:
    """Credit house funds when the bot wallet is below the configured floor.

    Uses ``BINGO_BOT_TOPUP`` ledger rows with ``reference_type=BINGO_BOT`` so
    admin user-detail can audit top-ups separately from player deposits.
    """

    from app.core.config import settings

    min_balance = Decimal(settings.BINGO_BOT_MIN_BALANCE)
    topup = Decimal(settings.BINGO_BOT_TOPUP_AMOUNT)

    db = SessionLocal()
    try:
        user = _load_user(db, user_id)
        if user is None:
            return "0"

        if user.balance >= min_balance:
            return str(user.balance)

        credit_wallet(
            db,
            user,
            amount=topup,
            transaction_type=BOT_TOPUP_TX_TYPE,
            description=f"Bingo house bot top-up (+{topup} ETB)",
            reference_type="BINGO_BOT",
        )
        db.commit()
        return str(user.balance)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def credit_bot_system_gain(
    bot_user_id: str,
    amount: Decimal,
    game_id: str,
) -> str | None:
    """Credit the house bot wallet with real-player stakes when the bot wins.

    Real players already lost their stakes via ``BINGO_STAKE`` on board select.
    This ledger row moves that revenue onto the bot balance (house liability)
    without paying a player-facing ``BINGO_WIN``. Returns the new balance
    string, or ``None`` if the amount is non-positive / user missing.
    """

    if amount <= 0:
        return None

    db = SessionLocal()
    try:
        user = _load_user(db, bot_user_id)
        if user is None:
            return None

        credit_wallet(
            db,
            user,
            amount=amount,
            transaction_type=BOT_SYSTEM_GAIN_TX_TYPE,
            description=(
                f"Bingo bot system gain ({game_id}) - real stakes +{amount} ETB"
            ),
            reference_type="BINGO_BOT",
        )
        db.commit()
        return str(user.balance)
    except Exception:
        db.rollback()
        raise
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
    system_fee: Decimal | None = None,
    public_winner_names: dict[str, str] | None = None,
    system_gain: Decimal | None = None,
    bot_won: bool = False,
    real_stake_total: Decimal | None = None,
    bot_stake_total: Decimal | None = None,
) -> None:
    """Mark a round finished and stamp winners/amounts onto their result rows.

    ``winners`` maps user_id -> total prize credited to that user.
    ``public_winner_names`` maps user_id -> player-facing display name (e.g. a
    durable dummy name for bot wins). Best-effort.

    ``system_fee`` is the prize-facing house cut (withheld from derash).
    ``system_gain`` is the admin-recognized P&L (bot-aware). When omitted,
    ``system_gain`` defaults to ``system_fee``.
    """

    names = public_winner_names or {}
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
        if system_fee is not None:
            game.system_fee = system_fee
        if system_gain is not None:
            game.system_gain = system_gain
        elif system_fee is not None:
            game.system_gain = system_fee
        game.bot_won = bool(bot_won)
        if real_stake_total is not None:
            game.real_stake_total = real_stake_total
        if bot_stake_total is not None:
            game.bot_stake_total = bot_stake_total

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
                public_name = (names.get(user_id) or "").strip()
                if public_name:
                    result.public_winner_name = public_name[:80]

        # Bot-only wins still stamp winner rows (amount 0) + public dummy name
        # so history / admin can see who won without a BINGO_WIN credit.
        if bot_won and not winners and names:
            for user_id, public_name in names.items():
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
                    result.amount_won = Decimal("0")
                    label = (public_name or "").strip()
                    if label:
                        result.public_winner_name = label[:80]

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


def get_user_history(
    user_id: str,
    limit: int = 10,
    offset: int = 0,
) -> dict:
    """Paginated finished/played rounds for a user, newest first.

    Only the requested page is loaded from Postgres. ``played`` / ``wins`` are
    aggregate counts over the user's full history so the Profile header stays
    accurate without fetching every row.
    """

    try:
        uid = UUID(user_id)
    except (ValueError, TypeError):
        return {"games": [], "total": 0, "played": 0, "wins": 0}

    safe_limit = max(1, min(int(limit), 50))
    safe_offset = max(0, int(offset))

    db = SessionLocal()

    try:
        base = (
            db.query(BingoGameResult, BingoGame)
            .join(BingoGame, BingoGameResult.game_id == BingoGame.id)
            .filter(BingoGameResult.user_id == uid)
        )

        total = base.count()
        wins = (
            db.query(BingoGameResult)
            .filter(
                BingoGameResult.user_id == uid,
                BingoGameResult.is_winner.is_(True),
            )
            .count()
        )

        rows = (
            base.order_by(BingoGame.created_at.desc())
            .offset(safe_offset)
            .limit(safe_limit)
            .all()
        )

        history: list[dict] = []
        game_ids = [game.id for _result, game in rows]

        winners_by_game: dict = {gid: [] for gid in game_ids}
        if game_ids:
            winner_rows = (
                db.query(
                    BingoGameResult.game_id,
                    BingoGameResult.public_winner_name,
                    User.first_name,
                )
                .join(User, User.id == BingoGameResult.user_id)
                .filter(
                    BingoGameResult.game_id.in_(game_ids),
                    BingoGameResult.is_winner.is_(True),
                )
                .all()
            )
            for game_id, public_name, first_name in winner_rows:
                # Prefer durable public label (bot dummy name); never leak
                # Bright Bot to player-facing history when a public name exists.
                name = (
                    (public_name or "").strip()
                    or (first_name or "Player").strip()
                    or "Player"
                )
                names = winners_by_game.setdefault(game_id, [])
                if name not in names:
                    names.append(name)

        for result, game in rows:
            gross = Decimal(game.derash)
            fee = Decimal(getattr(game, "system_fee", Decimal("0")) or 0)
            prize_pool = gross - fee
            history.append(
                {
                    "game_id": game.game_code,
                    "status": game.status,
                    "total_boards": game.total_boards,
                    "total_players": game.total_boards,
                    "derash": str(gross),
                    "system_fee": str(fee),
                    "prize_pool": str(prize_pool),
                    "boards_count": result.boards_count,
                    "stake": str(result.stake_amount),
                    "is_winner": result.is_winner,
                    "amount_won": str(result.amount_won),
                    "winning_pattern": game.winning_pattern,
                    "winner_count": game.winner_count,
                    "winner_names": winners_by_game.get(game.id, []),
                    "created_at": (
                        game.created_at.isoformat()
                        if game.created_at is not None
                        else None
                    ),
                }
            )

        return {
            "games": history,
            "total": total,
            "played": total,
            "wins": wins,
        }
    finally:
        db.close()
