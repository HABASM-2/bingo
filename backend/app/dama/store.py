"""Redis persistence for Dama presence, challenges, and matches."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.bingo.redis_store import get_redis
from app.dama.engine import Board, Side, create_initial_board

TURN_TIMEOUT_SECONDS = 120

ONLINE_KEY = "dama:online"
CHALLENGE_KEY = "dama:challenge:{challenge_id}"
CHALLENGE_TTL_SECONDS = 60
MATCH_KEY = "dama:match:{match_id}"
MATCH_TTL_SECONDS = 60 * 60 * 6
USER_MATCH_KEY = "dama:user_match:{user_id}"
LAST_MATCH_KEY = "dama:last_match:{user_id}"
LAST_MATCH_TTL_SECONDS = 30 * 60

PresenceStatus = Literal["idle", "challenging", "busy"]
MatchStatus = Literal["playing", "finished"]


@dataclass
class OnlinePlayer:
    user_id: str
    display_name: str
    photo_url: str | None = None
    status: PresenceStatus = "idle"
    match_id: str | None = None
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnlinePlayer:
        return cls(
            user_id=str(data["user_id"]),
            display_name=str(data.get("display_name") or "Player"),
            photo_url=data.get("photo_url"),
            status=data.get("status") or "idle",
            match_id=data.get("match_id"),
            last_seen=float(data.get("last_seen") or time.time()),
        )


@dataclass
class Challenge:
    id: str
    from_user_id: str
    from_name: str
    to_user_id: str
    to_name: str
    stake: str = "10"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Challenge:
        return cls(
            id=str(data["id"]),
            from_user_id=str(data["from_user_id"]),
            from_name=str(data.get("from_name") or "Player"),
            to_user_id=str(data["to_user_id"]),
            to_name=str(data.get("to_name") or "Player"),
            stake=str(data.get("stake") or "10"),
            created_at=float(data.get("created_at") or time.time()),
        )


@dataclass
class MatchState:
    id: str
    red_user_id: str
    red_name: str
    black_user_id: str
    black_name: str
    board: Board
    turn: Side = "red"
    status: MatchStatus = "playing"
    winner: Side | Literal["draw"] | None = None
    last_move: dict | None = None
    stake: str = "10"
    pot: str = "20"
    system_fee: str = "2"
    prize_pool: str = "18"
    game_code: str | None = None
    settled: bool = False
    ply_count: int = 0
    quiet_plies: int = 0
    draw_offer_by: str | None = None
    rematch_offer_by: str | None = None
    rematch_stake: str | None = None
    turn_deadline: float | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchState:
        return cls(
            id=str(data["id"]),
            red_user_id=str(data["red_user_id"]),
            red_name=str(data.get("red_name") or "Player"),
            black_user_id=str(data["black_user_id"]),
            black_name=str(data.get("black_name") or "Player"),
            board=data["board"],
            turn=data.get("turn") or "red",
            status=data.get("status") or "playing",
            winner=data.get("winner"),
            last_move=data.get("last_move"),
            stake=str(data.get("stake") or "10"),
            pot=str(data.get("pot") or "20"),
            system_fee=str(data.get("system_fee") or "0"),
            prize_pool=str(data.get("prize_pool") or "0"),
            game_code=data.get("game_code"),
            settled=bool(data.get("settled")),
            ply_count=int(data.get("ply_count") or 0),
            quiet_plies=int(data.get("quiet_plies") or 0),
            draw_offer_by=data.get("draw_offer_by"),
            rematch_offer_by=data.get("rematch_offer_by"),
            rematch_stake=data.get("rematch_stake"),
            turn_deadline=float(data["turn_deadline"]) if data.get("turn_deadline") else None,
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )

    def draw_eligible(self) -> bool:
        """Long / stuck games may offer a mutual draw."""
        if self.quiet_plies >= 30:
            return True
        if self.ply_count >= 50:
            return True
        pieces = [p for p in self.board if p]
        if not pieces:
            return True
        men = sum(1 for p in pieces if p.get("kind") == "man")
        if men == 0 and self.ply_count >= 20:
            return True
        return False

    def public_state(self, viewer_id: str) -> dict[str, Any]:
        my_side: Side | None = None
        if viewer_id == self.red_user_id:
            my_side = "red"
        elif viewer_id == self.black_user_id:
            my_side = "black"

        return {
            "type": "match_state",
            "match_id": self.id,
            "board": self.board,
            "turn": self.turn,
            "status": self.status,
            "winner": self.winner,
            "last_move": self.last_move,
            "my_side": my_side,
            "stake": self.stake,
            "pot": self.pot,
            "system_fee": self.system_fee,
            "prize_pool": self.prize_pool,
            "game_code": self.game_code,
            "ply_count": self.ply_count,
            "quiet_plies": self.quiet_plies,
            "draw_eligible": self.draw_eligible(),
            "draw_offer_by": self.draw_offer_by,
            "rematch_offer_by": self.rematch_offer_by,
            "rematch_stake": self.rematch_stake,
            "turn_deadline": self.turn_deadline,
            "red": {"user_id": self.red_user_id, "display_name": self.red_name},
            "black": {"user_id": self.black_user_id, "display_name": self.black_name},
        }


async def set_online(player: OnlinePlayer) -> None:
    redis = get_redis()
    player.last_seen = time.time()
    await redis.hset(ONLINE_KEY, player.user_id, json.dumps(player.to_dict()))


async def get_online(user_id: str) -> OnlinePlayer | None:
    redis = get_redis()
    raw = await redis.hget(ONLINE_KEY, user_id)
    if not raw:
        return None
    return OnlinePlayer.from_dict(json.loads(raw))


async def remove_online(user_id: str) -> None:
    redis = get_redis()
    await redis.hdel(ONLINE_KEY, user_id)


async def list_online() -> list[OnlinePlayer]:
    redis = get_redis()
    raw_map = await redis.hgetall(ONLINE_KEY)
    players = [OnlinePlayer.from_dict(json.loads(v)) for v in raw_map.values()]
    players.sort(key=lambda p: p.display_name.lower())
    return players


async def save_challenge(challenge: Challenge) -> None:
    redis = get_redis()
    key = CHALLENGE_KEY.format(challenge_id=challenge.id)
    await redis.set(key, json.dumps(challenge.to_dict()), ex=CHALLENGE_TTL_SECONDS)


async def get_challenge(challenge_id: str) -> Challenge | None:
    redis = get_redis()
    raw = await redis.get(CHALLENGE_KEY.format(challenge_id=challenge_id))
    if not raw:
        return None
    return Challenge.from_dict(json.loads(raw))


async def delete_challenge(challenge_id: str) -> None:
    redis = get_redis()
    await redis.delete(CHALLENGE_KEY.format(challenge_id=challenge_id))


async def save_match(match: MatchState) -> None:
    redis = get_redis()
    match.updated_at = time.time()
    key = MATCH_KEY.format(match_id=match.id)
    await redis.set(key, json.dumps(match.to_dict()), ex=MATCH_TTL_SECONDS)
    await redis.set(
        USER_MATCH_KEY.format(user_id=match.red_user_id),
        match.id,
        ex=MATCH_TTL_SECONDS,
    )
    await redis.set(
        USER_MATCH_KEY.format(user_id=match.black_user_id),
        match.id,
        ex=MATCH_TTL_SECONDS,
    )


async def get_match(match_id: str) -> MatchState | None:
    redis = get_redis()
    raw = await redis.get(MATCH_KEY.format(match_id=match_id))
    if not raw:
        return None
    return MatchState.from_dict(json.loads(raw))


async def get_user_match_id(user_id: str) -> str | None:
    redis = get_redis()
    return await redis.get(USER_MATCH_KEY.format(user_id=user_id))


async def clear_user_match(user_id: str) -> None:
    redis = get_redis()
    await redis.delete(USER_MATCH_KEY.format(user_id=user_id))


async def set_last_match(user_id: str, match_id: str) -> None:
    """Remember finished match so rematch / leave notices still work."""
    redis = get_redis()
    await redis.set(
        LAST_MATCH_KEY.format(user_id=user_id),
        match_id,
        ex=LAST_MATCH_TTL_SECONDS,
    )


async def get_last_match_id(user_id: str) -> str | None:
    redis = get_redis()
    return await redis.get(LAST_MATCH_KEY.format(user_id=user_id))


async def clear_last_match(user_id: str) -> None:
    redis = get_redis()
    await redis.delete(LAST_MATCH_KEY.format(user_id=user_id))


def new_challenge_id() -> str:
    return uuid.uuid4().hex


def new_match_id() -> str:
    return uuid.uuid4().hex


def create_match(
    *,
    red_user_id: str,
    red_name: str,
    black_user_id: str,
    black_name: str,
    stake: str = "10",
    pot: str = "20",
    system_fee: str = "2",
    prize_pool: str = "18",
    game_code: str | None = None,
    match_id: str | None = None,
) -> MatchState:
    return MatchState(
        id=match_id or new_match_id(),
        red_user_id=red_user_id,
        red_name=red_name,
        black_user_id=black_user_id,
        black_name=black_name,
        board=create_initial_board(),
        turn="red",
        status="playing",
        stake=stake,
        pot=pot,
        system_fee=system_fee,
        prize_pool=prize_pool,
        game_code=game_code,
        turn_deadline=time.time() + TURN_TIMEOUT_SECONDS,
    )
