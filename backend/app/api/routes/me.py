"""Authenticated /me endpoints for Profile tab data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import profile_service
from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.models.user import User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile-summary")
def get_profile_summary(
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Light profile metadata (no heavy per-game history arrays)."""
    return profile_service.profile_summary(db, user.id, limit=limit)


@router.get("/history")
def get_history(
    game: str = Query(..., pattern="^(bingo|dama|aviator|plinko|lotto)$"),
    limit: int = Query(5, ge=1, le=20),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated history for one game title: {items, total, limit, offset}."""
    try:
        return profile_service.game_history(
            db, user.id, game=game, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/payments")
def get_payments(
    type: str = Query(..., pattern="^(deposit|withdraw)$"),
    limit: int = Query(5, ge=1, le=20),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current user's deposit or withdraw rows only (never other users)."""
    if type == "deposit":
        return profile_service.list_deposits(db, user.id, limit=limit, offset=offset)
    if type == "withdraw":
        return profile_service.list_withdrawals(db, user.id, limit=limit, offset=offset)
    raise HTTPException(status_code=400, detail="type must be deposit or withdraw")
