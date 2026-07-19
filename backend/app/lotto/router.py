"""Authenticated Lotto Spin REST API."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.lotto import service
from app.lotto.game_loop import ensure_game_loop
from app.lotto.manager import hub
from app.models.user import User

router = APIRouter(prefix="/lotto", tags=["lotto"])


class ReserveRequest(BaseModel):
    stake_room: Decimal
    numbers: list[int] = Field(min_length=1, max_length=service.CAPACITY)
    request_id: UUID


@router.get("/snapshot")
@router.get("/rooms")
def rooms(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.snapshot(db)


@router.post("/reserve")
async def reserve(
    payload: ReserveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = service.reserve(
            db,
            user_id=user.id,
            raw_stake=payload.stake_room,
            raw_numbers=payload.numbers,
            request_id=payload.request_id,
        )
    except service.LottoError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    ensure_game_loop()
    await hub.broadcast(
        {
            "type": "room_updated",
            "server_time": service.utcnow().isoformat(),
            "room": result["round"],
        }
    )
    # This is sent only to this user's sockets; room broadcasts never contain it.
    await hub.send_user(
        str(user.id), {"type": "wallet", "balance": result["balance"]}
    )
    # Pre-draw notices when this reservation filled the room (idempotent).
    if (
        not result.get("replayed")
        and result.get("round", {}).get("status") == "countdown"
    ):
        from app.lotto import notifications as lotto_notify

        lotto_notify.schedule_pre_draw(result["round"]["id"])
    return result


@router.get("/history")
def lotto_history(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.history(db, user.id, limit, offset)
