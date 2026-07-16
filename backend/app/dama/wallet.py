"""Dama wallet: stakes, prizes, and profile history."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from app.db.database import SessionLocal
from app.models.dama_game import DamaGame, DamaGameResult
from app.models.user import User
from app.services.wallet_service import credit_wallet

STAKE_TX_TYPE = "DAMA_STAKE"
WIN_TX_TYPE = "DAMA_WIN"
REFUND_TX_TYPE = "DAMA_REFUND"

# House cut on the pot (2 × stake). Winner receives the rest.
FEE_RATE = Decimal("0.10")

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


def pot_for(stake: Decimal) -> Decimal:
    return (stake * 2).quantize(Decimal("0.01"))


def fee_for(pot: Decimal) -> Decimal:
    return (pot * FEE_RATE).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def prize_for(pot: Decimal, fee: Decimal) -> Decimal:
    return (pot - fee).quantize(Decimal("0.01"))


def _load_user(db, user_id: str) -> User | None:
    try:
        return db.query(User).filter(User.id == UUID(user_id)).first()
    except (ValueError, TypeError):
        return None


def _game_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "DM" + "".join(secrets.choice(alphabet) for _ in range(8))


def get_balance(user_id: str) -> str | None:
    db = SessionLocal()
    try:
        user = _load_user(db, user_id)
        return str(user.balance) if user else None
    finally:
        db.close()


def charge_users(user_ids: list[str], stake: Decimal, game_code: str) -> dict[str, str]:
    """Debit each user ``stake``. All-or-nothing: if anyone can't pay, none are charged."""

    if stake <= 0 or not user_ids:
        return {}

    db = SessionLocal()
    try:
        users: list[User] = []
        for uid in user_ids:
            user = _load_user(db, uid)
            if user is None or user.balance < stake:
                return {}
            users.append(user)

        paid: dict[str, str] = {}
        for user in users:
            credit_wallet(
                db,
                user,
                amount=-stake,
                transaction_type=STAKE_TX_TYPE,
                description=f"Dama stake ({game_code}) - {stake} ETB",
                reference_type="DAMA",
            )
            paid[str(user.id)] = str(user.balance)

        db.commit()
        return paid
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def refund_users(user_ids: list[str], stake: Decimal, game_code: str) -> dict[str, str]:
    if stake <= 0 or not user_ids:
        return {}

    db = SessionLocal()
    try:
        balances: dict[str, str] = {}
        for uid in user_ids:
            user = _load_user(db, uid)
            if user is None:
                continue
            credit_wallet(
                db,
                user,
                amount=stake,
                transaction_type=REFUND_TX_TYPE,
                description=f"Dama refund ({game_code}) - {stake} ETB",
                reference_type="DAMA",
            )
            balances[uid] = str(user.balance)
        db.commit()
        return balances
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def award_prize(user_id: str, amount: Decimal, game_code: str) -> str | None:
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
            description=f"Dama win ({game_code}) - {amount} ETB",
            reference_type="DAMA",
        )
        db.commit()
        return str(user.balance)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def start_ai_game(user_id: str, stake: Decimal) -> dict:
    """Charge player stake and open an AI match. House matches the stake conceptually."""

    stake = parse_stake(stake)
    pot = pot_for(stake)
    fee = fee_for(pot)
    prize = prize_for(pot, fee)
    code = _game_code()

    paid = charge_users([user_id], stake, code)
    if user_id not in paid:
        raise ValueError("Insufficient balance")

    db = SessionLocal()
    try:
        game = DamaGame(
            game_code=code,
            mode="ai",
            status="in_progress",
            stake=stake,
            pot=pot,
            system_fee=fee,
            prize_pool=prize,
            match_id=code,
        )
        db.add(game)
        db.flush()
        db.add(
            DamaGameResult(
                game_id=game.id,
                user_id=UUID(user_id),
                stake_amount=stake,
                is_winner=False,
                amount_won=Decimal("0"),
                outcome="loss",
            )
        )
        db.commit()
        return {
            "game_code": code,
            "stake": str(stake),
            "pot": str(pot),
            "system_fee": str(fee),
            "prize_pool": str(prize),
            "balance": paid[user_id],
        }
    except Exception:
        db.rollback()
        # Best-effort refund if history insert failed after charge.
        try:
            refund_users([user_id], stake, code)
        except Exception:
            pass
        raise
    finally:
        db.close()


def finish_ai_game(user_id: str, game_code: str, outcome: str) -> dict:
    """Settle AI match. ``outcome`` is win | loss | draw for the human."""

    if outcome not in ("win", "loss", "draw"):
        raise ValueError("Invalid outcome")

    db = SessionLocal()
    try:
        game = db.query(DamaGame).filter(DamaGame.game_code == game_code).first()
        if game is None or game.mode != "ai":
            raise ValueError("Game not found")
        if game.status != "in_progress":
            # Idempotent: already settled.
            return {
                "game_code": game.game_code,
                "status": game.status,
                "prize_pool": str(game.prize_pool),
                "already_finished": True,
            }

        result = (
            db.query(DamaGameResult)
            .filter(
                DamaGameResult.game_id == game.id,
                DamaGameResult.user_id == UUID(user_id),
            )
            .first()
        )
        if result is None:
            raise ValueError("Not your game")

        game.status = "finished"
        game.finished_at = datetime.now(timezone.utc)
        prize = Decimal("0")
        balances: dict[str, str] = {}

        if outcome == "win":
            prize = game.prize_pool
            game.winner_user_id = UUID(user_id)
            game.winner_side = "red"
            result.is_winner = True
            result.amount_won = prize
            result.outcome = "win"
            db.commit()
            bal = award_prize(user_id, prize, game.game_code)
            if bal:
                balances[user_id] = bal
        elif outcome == "draw":
            game.winner_side = "draw"
            result.outcome = "draw"
            result.amount_won = game.stake
            db.commit()
            bal = refund_users([user_id], game.stake, game.game_code)
            balances.update(bal)
        else:
            game.winner_side = "black"
            result.outcome = "loss"
            db.commit()

        return {
            "game_code": game.game_code,
            "status": "finished",
            "outcome": outcome,
            "prize_pool": str(game.prize_pool),
            "amount_won": str(prize if outcome == "win" else (game.stake if outcome == "draw" else 0)),
            "balances": balances,
            "already_finished": False,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def start_online_game(
    *,
    red_user_id: str,
    black_user_id: str,
    stake: Decimal,
    match_id: str,
) -> dict:
    stake = parse_stake(stake)
    pot = pot_for(stake)
    fee = fee_for(pot)
    prize = prize_for(pot, fee)
    code = _game_code()

    paid = charge_users([red_user_id, black_user_id], stake, code)
    if red_user_id not in paid or black_user_id not in paid:
        raise ValueError("Both players need enough balance for this stake")

    db = SessionLocal()
    try:
        game = DamaGame(
            game_code=code,
            mode="online",
            status="in_progress",
            stake=stake,
            pot=pot,
            system_fee=fee,
            prize_pool=prize,
            match_id=match_id,
        )
        db.add(game)
        db.flush()
        for uid in (red_user_id, black_user_id):
            db.add(
                DamaGameResult(
                    game_id=game.id,
                    user_id=UUID(uid),
                    stake_amount=stake,
                    is_winner=False,
                    amount_won=Decimal("0"),
                    outcome="loss",
                )
            )
        db.commit()
        return {
            "game_code": code,
            "stake": str(stake),
            "pot": str(pot),
            "system_fee": str(fee),
            "prize_pool": str(prize),
            "balances": paid,
        }
    except Exception:
        db.rollback()
        try:
            refund_users([red_user_id, black_user_id], stake, code)
        except Exception:
            pass
        raise
    finally:
        db.close()


def settle_online_game(
    *,
    match_id: str,
    winner_side: str | None,
    red_user_id: str,
    black_user_id: str,
) -> dict:
    """Settle by Redis match_id. winner_side: red | black | draw."""

    db = SessionLocal()
    try:
        game = (
            db.query(DamaGame)
            .filter(DamaGame.match_id == match_id, DamaGame.mode == "online")
            .order_by(DamaGame.created_at.desc())
            .first()
        )
        if game is None:
            return {"ok": False, "reason": "missing"}
        if game.status != "in_progress":
            return {
                "ok": True,
                "already_finished": True,
                "game_code": game.game_code,
                "prize_pool": str(game.prize_pool),
            }

        game.status = "finished"
        game.finished_at = datetime.now(timezone.utc)
        game.winner_side = winner_side

        results = {
            str(r.user_id): r
            for r in db.query(DamaGameResult).filter(DamaGameResult.game_id == game.id)
        }

        balances: dict[str, str] = {}
        prize = Decimal("0")

        if winner_side == "draw":
            for uid in (red_user_id, black_user_id):
                r = results.get(uid)
                if r:
                    r.outcome = "draw"
                    r.amount_won = game.stake
            db.commit()
            balances = refund_users([red_user_id, black_user_id], game.stake, game.game_code)
        elif winner_side in ("red", "black"):
            winner_id = red_user_id if winner_side == "red" else black_user_id
            loser_id = black_user_id if winner_side == "red" else red_user_id
            prize = game.prize_pool
            game.winner_user_id = UUID(winner_id)
            wr = results.get(winner_id)
            lr = results.get(loser_id)
            if wr:
                wr.is_winner = True
                wr.amount_won = prize
                wr.outcome = "win"
            if lr:
                lr.outcome = "loss"
            db.commit()
            bal = award_prize(winner_id, prize, game.game_code)
            if bal:
                balances[winner_id] = bal
        else:
            db.commit()

        return {
            "ok": True,
            "already_finished": False,
            "game_code": game.game_code,
            "prize_pool": str(game.prize_pool),
            "system_fee": str(game.system_fee),
            "winner_side": winner_side,
            "balances": balances,
            "amount_won": str(prize),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_user_history(user_id: str, limit: int = 10, offset: int = 0) -> dict:
    db = SessionLocal()
    try:
        uid = UUID(user_id)
        base = (
            db.query(DamaGameResult, DamaGame)
            .join(DamaGame, DamaGameResult.game_id == DamaGame.id)
            .filter(DamaGameResult.user_id == uid)
            .order_by(DamaGame.created_at.desc())
        )
        total = base.count()
        wins = (
            db.query(DamaGameResult)
            .filter(DamaGameResult.user_id == uid, DamaGameResult.is_winner.is_(True))
            .count()
        )
        rows = base.offset(offset).limit(limit).all()

        games = []
        for result, game in rows:
            games.append(
                {
                    "game_id": game.game_code,
                    "mode": game.mode,
                    "status": game.status,
                    "stake": str(result.stake_amount),
                    "pot": str(game.pot),
                    "system_fee": str(game.system_fee),
                    "prize_pool": str(game.prize_pool),
                    "is_winner": result.is_winner,
                    "amount_won": str(result.amount_won),
                    "outcome": result.outcome,
                    "created_at": game.created_at.isoformat() if game.created_at else None,
                }
            )

        return {
            "games": games,
            "total": total,
            "played": total,
            "wins": wins,
        }
    finally:
        db.close()
