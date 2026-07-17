"""Authenticated Plinko API."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.models.user import User
from app.plinko import service
from app.plinko.config import (
    ALLOWED_RISKS,
    ALLOWED_ROWS,
    MAX_STAKE,
    MIN_STAKE,
    MULTIPLIER_TABLES,
    expected_rtp,
)

router = APIRouter(prefix="/plinko", tags=["plinko"])


class PlayRequest(BaseModel):
    play_id: UUID
    amount: Decimal = Field(ge=0)
    risk: str
    rows: int


@router.post("/play")
def play_plinko(
    payload: PlayRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return service.play(
            db,
            user_id=user.id,
            play_id=payload.play_id,
            raw_stake=payload.amount,
            risk=payload.risk,
            rows=payload.rows,
        )
    except ValueError as exc:
        message = str(exc)
        status = 409 if message == "Insufficient balance" else 422
        raise HTTPException(status_code=status, detail=message) from exc


@router.get("/history")
def plinko_history(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.history(db, user.id, limit, offset)


@router.get("/presets")
def presets(_: User = Depends(get_current_user)):
    return {
        "rows": list(ALLOWED_ROWS),
        "risks": list(ALLOWED_RISKS),
        "min": str(MIN_STAKE),
        "max": str(MAX_STAKE),
        "tables": {
            risk: {
                str(rows): [str(value) for value in MULTIPLIER_TABLES[risk][rows]]
                for rows in ALLOWED_ROWS
            }
            for risk in ALLOWED_RISKS
        },
        "rtp": {
            risk: {str(rows): str(expected_rtp(rows, risk)) for rows in ALLOWED_ROWS}
            for risk in ALLOWED_RISKS
        },
    }
