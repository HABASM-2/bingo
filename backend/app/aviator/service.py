"""Aviator round business logic."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from app.aviator import store
from app.aviator import wallet as aviator_wallet
from app.aviator.crash import (
    MIN_CASHOUT_MULT,
    START_MULT,
    cashout_payout,
    multiplier_at,
)
from app.aviator.manager import hub


class AviatorError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@asynccontextmanager
async def _round_mutation_lock(round_id: str):
    """Serialize bet/cash-out mutations so balances and the pool cannot race."""
    from app.bingo.redis_store import get_redis

    redis = get_redis()
    key = f"aviator:round:{round_id}:mutation"
    token = uuid.uuid4().hex
    acquired = False
    for _ in range(40):
        if await redis.set(key, token, nx=True, px=10000):
            acquired = True
            break
        await asyncio.sleep(0.025)
    if not acquired:
        raise AviatorError("Round is busy — please try again")

    try:
        yield
    finally:
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )


def _public_round(round: store.LiveRound, current_mult: float | None = None) -> dict:
    payload = round.to_dict()
    payload["type"] = "round_state"
    if current_mult is not None:
        payload["multiplier"] = current_mult
    return payload


def _betting_seconds_left(round: store.LiveRound) -> float:
    if round.betting_ends_at is None:
        return 0.0
    return max(0.0, round.betting_ends_at - time.time())


def current_multiplier(round: store.LiveRound) -> float:
    if round.phase != "flying" or not round.flying_started_at:
        return START_MULT
    elapsed = time.time() - round.flying_started_at
    mult = multiplier_at(elapsed)
    if round.crash_multiplier:
        mult = min(mult, round.crash_multiplier)
    return mult


async def end_flying_round(rnd: store.LiveRound, crash_mult: float) -> None:
    rnd.phase = "crashed"
    rnd.crash_multiplier = crash_mult
    await store.save_round(rnd)
    await settle_round(rnd)
    await broadcast_phase(rnd, crash_mult)


async def snapshot() -> dict:
    rnd = await store.get_current_round()
    history = await store.get_history()
    if rnd is None:
        return {"type": "round_state", "phase": "waiting", "history": history, "bets": []}
    mult = current_multiplier(rnd) if rnd.phase == "flying" else None
    payload = _public_round(rnd, mult)
    payload["history"] = history
    payload["betting_seconds_left"] = _betting_seconds_left(rnd)
    return payload


async def place_bet(
    user_id: str,
    display_name: str,
    stake_raw,
    slot: int = 0,
) -> dict:
    rnd = await store.get_current_round()
    if rnd is None or rnd.phase != "betting":
        raise AviatorError("Betting is closed — wait for the next round")
    if slot != 0:
        raise AviatorError("Only one bet is allowed per round")

    stake = aviator_wallet.parse_stake(stake_raw)
    async with _round_mutation_lock(rnd.round_id):
        rnd = await store.get_current_round()
        if rnd is None or rnd.phase != "betting" or _betting_seconds_left(rnd) <= 0:
            raise AviatorError("Betting window closed")
        if any(b.user_id == user_id for b in rnd.bets):
            raise AviatorError("You already have a bet this round")

        balance = await asyncio.to_thread(
            aviator_wallet.charge_bet, user_id, stake, rnd.round_code
        )

        bet = store.LiveBet(
            bet_id=uuid.uuid4().hex,
            user_id=user_id,
            display_name=display_name,
            stake=str(stake),
            slot=0,
        )
        rnd.bets.append(bet)
        store.recalc_totals(rnd)
        await store.save_round(rnd)

    msg = {
        "type": "bet_placed",
        "bet": bet.to_dict(),
        "round": rnd.to_dict(),
    }
    await hub.broadcast(msg)
    return {**msg, "balance": balance}


async def cash_out(user_id: str, bet_id: str | None = None, slot: int | None = None) -> dict:
    rnd = await store.get_current_round()
    if rnd is None or rnd.phase != "flying":
        raise AviatorError("Cannot cash out now")

    async with _round_mutation_lock(rnd.round_id):
        rnd = await store.get_current_round()
        if rnd is None or rnd.phase != "flying":
            raise AviatorError("Cannot cash out now")

        mult_live = current_multiplier(rnd)
        if rnd.crash_multiplier is not None and mult_live >= rnd.crash_multiplier:
            raise AviatorError("Too late — plane flew away")
        if mult_live < MIN_CASHOUT_MULT:
            raise AviatorError(f"Wait until at least {MIN_CASHOUT_MULT:.2f}x to cash out")

        target: store.LiveBet | None = None
        for b in rnd.bets:
            if b.user_id != user_id or b.status != "active":
                continue
            if bet_id and b.bet_id == bet_id:
                target = b
                break
            if slot is not None and b.slot == slot:
                target = b
                break
            if bet_id is None and slot is None:
                target = b
                break

        if target is None:
            raise AviatorError("Bet already cashed out or no active bet exists")

        stake = Decimal(target.stake)
        win = cashout_payout(stake, mult_live)
        if win <= 0:
            raise AviatorError("Invalid cash-out amount")

        balance = await asyncio.to_thread(
            aviator_wallet.credit_cashout,
            user_id,
            win,
            rnd.round_code,
            target.bet_id,
        )

        target.status = "cashed"
        target.cashout_at = float(mult_live)
        target.win = str(win)
        store.recalc_totals(rnd)
        await store.save_round(rnd)

    msg = {
        "type": "cashout",
        "bet_id": target.bet_id,
        "user_id": user_id,
        "cashout_at": float(mult_live),
        "win": str(win),
        "multiplier": mult_live,
        "round": rnd.to_dict(),
    }
    await hub.broadcast(msg)

    return {**msg, "balance": balance}


async def settle_round(rnd: store.LiveRound) -> None:
    """Mark uncashed bets as lost and persist to Postgres."""
    for b in rnd.bets:
        if b.status == "active":
            b.status = "lost"

    store.recalc_totals(rnd)
    crash = rnd.crash_multiplier or START_MULT

    await asyncio.to_thread(
        aviator_wallet.record_round_finish,
        round_code=rnd.round_code,
        crash_multiplier=crash,
        player_count=rnd.player_count(),
        total_stake=Decimal(rnd.total_stake),
        total_payout=Decimal(rnd.total_payout),
        max_payout_mult=Decimal("0"),
        bets=[b.to_dict() for b in rnd.bets],
    )

    await store.push_history(crash)
    await store.save_round(rnd)


async def broadcast_tick(rnd: store.LiveRound) -> None:
    mult = current_multiplier(rnd)
    await hub.broadcast(
        {
            "type": "tick",
            "round_id": rnd.round_id,
            "multiplier": mult,
            "phase": rnd.phase,
        }
    )


async def broadcast_phase(rnd: store.LiveRound, mult: float | None = None) -> None:
    payload = _public_round(rnd, mult)
    payload["type"] = "phase"
    payload["history"] = await store.get_history()
    payload["betting_seconds_left"] = _betting_seconds_left(rnd)
    await hub.broadcast(payload)
