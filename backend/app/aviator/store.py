"""Redis live state for the global Aviator round."""

from __future__ import annotations

import json
import secrets
import string
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal

from app.bingo.redis_store import get_redis
from app.aviator.crash import pool_remaining

ROUND_KEY = "aviator:round:current"
HISTORY_KEY = "aviator:history"
HISTORY_MAX = 30
ROUND_TTL = 3600

Phase = Literal["betting", "flying", "crashed"]


@dataclass
class LiveBet:
    bet_id: str
    user_id: str
    display_name: str
    stake: str
    slot: int
    status: Literal["active", "cashed", "lost"] = "active"
    cashout_at: float | None = None
    win: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveBet:
        return cls(
            bet_id=str(data["bet_id"]),
            user_id=str(data["user_id"]),
            display_name=str(data.get("display_name") or "Player"),
            stake=str(data["stake"]),
            slot=int(data.get("slot") or 0),
            status=data.get("status") or "active",
            cashout_at=float(data["cashout_at"]) if data.get("cashout_at") else None,
            win=str(data["win"]) if data.get("win") is not None else None,
        )


@dataclass
class LiveRound:
    round_id: str
    round_code: str
    phase: Phase
    crash_multiplier: float | None = None
    betting_ends_at: float | None = None
    flying_started_at: float | None = None
    total_stake: str = "0"
    total_payout: str = "0"
    bets: list[LiveBet] = field(default_factory=list)
    db_round_id: str | None = None

    def player_count(self) -> int:
        return len({b.user_id for b in self.bets})

    def pool_left(self) -> Decimal:
        return pool_remaining(Decimal(self.total_stake), Decimal(self.total_payout))

    def to_dict(self) -> dict[str, Any]:
        left = self.pool_left()
        return {
            "round_id": self.round_id,
            "round_code": self.round_code,
            "phase": self.phase,
            "crash_multiplier": self.crash_multiplier,
            "betting_ends_at": self.betting_ends_at,
            "flying_started_at": self.flying_started_at,
            "total_stake": self.total_stake,
            "total_payout": self.total_payout,
            "pool_remaining": str(left),
            "player_count": self.player_count(),
            "bets": [b.to_dict() for b in self.bets],
            "db_round_id": self.db_round_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveRound:
        bets = [LiveBet.from_dict(b) for b in data.get("bets") or []]
        return cls(
            round_id=str(data["round_id"]),
            round_code=str(data["round_code"]),
            phase=data.get("phase") or "betting",
            crash_multiplier=float(data["crash_multiplier"]) if data.get("crash_multiplier") else None,
            betting_ends_at=float(data["betting_ends_at"]) if data.get("betting_ends_at") else None,
            flying_started_at=float(data["flying_started_at"]) if data.get("flying_started_at") else None,
            total_stake=str(data.get("total_stake") or "0"),
            total_payout=str(data.get("total_payout") or "0"),
            bets=bets,
            db_round_id=data.get("db_round_id"),
        )


def _round_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "AV" + "".join(secrets.choice(alphabet) for _ in range(8))


async def get_current_round() -> LiveRound | None:
    redis = get_redis()
    raw = await redis.get(ROUND_KEY)
    if not raw:
        return None
    return LiveRound.from_dict(json.loads(raw))


async def save_round(round: LiveRound) -> None:
    redis = get_redis()
    await redis.set(ROUND_KEY, json.dumps(round.to_dict()), ex=ROUND_TTL)


async def create_round(betting_seconds: float, db_round_id: str | None = None) -> LiveRound:
    now = time.time()
    rnd = LiveRound(
        round_id=uuid.uuid4().hex,
        round_code=_round_code(),
        phase="betting",
        betting_ends_at=now + betting_seconds,
        db_round_id=db_round_id,
    )
    await save_round(rnd)
    return rnd


async def push_history(crash_mult: float) -> list[float]:
    redis = get_redis()
    await redis.lpush(HISTORY_KEY, str(crash_mult))
    await redis.ltrim(HISTORY_KEY, 0, HISTORY_MAX - 1)
    raw = await redis.lrange(HISTORY_KEY, 0, HISTORY_MAX - 1)
    return [float(x) for x in raw]


async def get_history() -> list[float]:
    redis = get_redis()
    raw = await redis.lrange(HISTORY_KEY, 0, HISTORY_MAX - 1)
    if not raw:
        return [1.24, 1.43, 2.07, 1.18, 3.44, 1.09, 5.21, 1.67, 13.54]
    return [float(x) for x in raw]


def recalc_totals(round: LiveRound) -> None:
    total = Decimal("0")
    paid = Decimal("0")
    for b in round.bets:
        total += Decimal(b.stake)
        if b.win:
            paid += Decimal(b.win)
    round.total_stake = str(total.quantize(Decimal("0.01")))
    round.total_payout = str(paid.quantize(Decimal("0.01")))
