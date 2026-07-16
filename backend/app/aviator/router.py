"""REST API for Aviator presets and history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.current_user import get_current_user
from app.aviator import wallet as aviator_wallet
from app.models.user import User

router = APIRouter(prefix="/aviator", tags=["aviator"])


@router.get("/presets")
def stake_presets():
    return {
        "presets": [str(s) for s in aviator_wallet.PRESET_STAKES],
        "min": str(aviator_wallet.MIN_STAKE),
        "max": str(aviator_wallet.MAX_STAKE),
        "betting_seconds": 5,
        "start_multiplier": "1.00",
    }


@router.get("/history")
def history(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    return aviator_wallet.get_user_history(str(user.id), limit=limit, offset=offset)


@router.get("/leaderboard")
def leaderboard(
    limit: int = Query(20, ge=1, le=50),
    _: User = Depends(get_current_user),
):
    return aviator_wallet.get_top_gainers(limit=limit)
