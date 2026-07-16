"""REST convenience endpoints for Bingo rooms.

Real-time gameplay (drawing, daubing, claiming) happens over the WebSocket
in ``app.bingo.ws``; these endpoints exist so the frontend Lobby can
list/create rooms and buy cartelas with a plain HTTP call before (or
without) opening a socket. Both surfaces share ``app.bingo.service`` so
state can never disagree between them.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.current_user import get_current_user
from app.bingo import redis_store, service, wallet
from app.bingo.schemas import (
    CreateRoomRequest,
    GameHistoryResponse,
    JoinRoomResponse,
    RoomListResponse,
    RoomSummary,
)
from app.bingo.service import BingoError
from app.core.config import settings
from app.models.user import User

router = APIRouter(
    prefix="/bingo",
    tags=["Bingo"],
)


@router.get("/lobby", response_model=RoomSummary)
async def lobby():
    """The single shared public lobby every player joins.

    Creation is atomic (see ``service.get_or_create_default_room``) so
    concurrent first-time visitors can never spawn separate rooms and end up
    unable to see each other.
    """

    room = await service.get_or_create_default_room()

    return service.room_summary(room)


@router.get("/history", response_model=GameHistoryResponse)
async def history(
    user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Paginated Bingo rounds the authenticated user staked in, newest first.

    Sourced entirely from Postgres (``bingo_games`` / ``bingo_game_results``)
    so the History tab reflects real, persisted rounds - stakes paid, boards
    played, and any derash won. Only the requested page is loaded.
    """

    payload = await asyncio.to_thread(
        wallet.get_user_history,
        str(user.id),
        limit,
        offset,
    )

    return payload


@router.get("/rooms", response_model=RoomListResponse)
async def list_rooms():
    rooms = await redis_store.list_rooms()

    return {"rooms": [service.room_summary(room) for room in rooms]}


@router.post("/rooms", response_model=RoomSummary)
async def create_room(request: CreateRoomRequest):
    room = await redis_store.create_room(
        name=request.name,
        entry_fee=request.entry_fee or settings.BINGO_DEFAULT_ENTRY_FEE,
    )

    return service.room_summary(room)


@router.get("/rooms/{room_id}", response_model=RoomSummary)
async def get_room(room_id: str):
    room = await redis_store.get_room(room_id)

    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    return service.room_summary(room)


@router.post("/rooms/{room_id}/join", response_model=JoinRoomResponse)
async def join_room(
    room_id: str,
    user: User = Depends(get_current_user),
):
    try:
        room = await service.join_room(
            room_id,
            str(user.id),
            user.first_name or user.username or "Player",
            str(user.balance),
        )
    except BingoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "room_id": room.room_id,
        "ws_path": f"/ws/bingo/{room.room_id}",
        "entry_fee": room.entry_fee,
        "player_balance": str(user.balance),
        "max_cards_per_player": room.max_cards_per_player,
        "status": room.status,
        "player_count": room.connected_player_count(),
    }
