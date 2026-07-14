"""REST + WebSocket payload types for the Bingo module.

``entry_fee`` and ``player_balance`` are wired through end-to-end even
though play is currently free - monetizing later should only require
enforcing them, not adding new fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CardGrid = list[list[int | None]]
RoomStatus = Literal["lobby", "in_progress", "finished"]


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

class RoomSummary(BaseModel):
    room_id: str
    name: str
    status: RoomStatus
    player_count: int
    max_cards_per_player: int
    entry_fee: str = "0"
    drawn_count: int = 0
    current_ball: int | None = None


class RoomListResponse(BaseModel):
    rooms: list[RoomSummary]


class CreateRoomRequest(BaseModel):
    name: str = Field(default="Bingo Room", max_length=64)
    entry_fee: str = Field(default="0")


class JoinRoomResponse(BaseModel):
    room_id: str
    ws_path: str
    entry_fee: str
    player_balance: str
    max_cards_per_player: int
    status: RoomStatus
    player_count: int


class CardOut(BaseModel):
    card_id: str
    numbers: CardGrid
    marks: list[list[bool]]


class GameHistoryEntry(BaseModel):
    game_id: str
    status: str
    total_boards: int
    total_players: int
    derash: str
    boards_count: int
    stake: str
    is_winner: bool
    amount_won: str
    winning_pattern: str | None = None
    created_at: str | None = None


class GameHistoryResponse(BaseModel):
    games: list[GameHistoryEntry]


# ---------------------------------------------------------------------------
# WebSocket - client -> server
# ---------------------------------------------------------------------------

class WSJoinMessage(BaseModel):
    type: Literal["join"] = "join"


class WSSelectBoardMessage(BaseModel):
    type: Literal["select_board"] = "select_board"
    board_id: int


class WSDeselectBoardMessage(BaseModel):
    type: Literal["deselect_board"] = "deselect_board"
    board_id: int


class WSDeselectAllMessage(BaseModel):
    type: Literal["deselect_all"] = "deselect_all"


class WSClaimBingoMessage(BaseModel):
    type: Literal["claim_bingo"] = "claim_bingo"
    card_id: str


class WSPingMessage(BaseModel):
    type: Literal["ping"] = "ping"


# ---------------------------------------------------------------------------
# WebSocket - server -> client
# ---------------------------------------------------------------------------

class RoomPlayerView(BaseModel):
    user_id: str
    display_name: str
    cards_count: int
    connected: bool
    is_host: bool


class WinnerInfo(BaseModel):
    user_id: str
    name: str
    card_id: str
    pattern: str


class RoomStateMessage(BaseModel):
    type: Literal["room_state"] = "room_state"
    room_id: str
    name: str
    status: RoomStatus
    players: list[RoomPlayerView]
    cards: list[CardOut]
    drawn: list[int]
    current_ball: int | None
    entry_fee: str
    player_balance: str
    max_cards_per_player: int
    winner: str | None = None
    winner_name: str | None = None
    winning_pattern: str | None = None
    winning_card_id: str | None = None
    winners: list[WinnerInfo] = []
    derash_share: str = "0"
    board_price: str = "10"
    max_boards: int = 2
    board_pool_max: int = 400
    my_boards: list[int] = []
    taken_boards: list[int] = []
    seconds_left: int = 0
    game_id: str | None = None
    derash: str = "0"
    players_in_round: int = 0
    call_count: int = 0


class PlayerCountMessage(BaseModel):
    type: Literal["player_count"] = "player_count"
    count: int


class LobbyTickMessage(BaseModel):
    type: Literal["lobby_tick"] = "lobby_tick"
    seconds_left: int


class ToastMessage(BaseModel):
    type: Literal["toast"] = "toast"
    message: str


class BallMessage(BaseModel):
    type: Literal["ball"] = "ball"
    number: int
    drawn: list[int]


class BingoResultMessage(BaseModel):
    type: Literal["bingo_result"] = "bingo_result"
    valid: bool
    winner: str | None = None
    pattern: str | None = None
    card_id: str | None = None
    reason: str | None = None


class GameOverMessage(BaseModel):
    type: Literal["game_over"] = "game_over"
    winner: str | None
    winner_name: str | None = None
    pattern: str | None = None
    winning_card_id: str | None = None
    derash: str = "0"
    derash_share: str = "0"
    winners: list[WinnerInfo] = []
    winner_count: int = 0


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"
