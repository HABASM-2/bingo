"""REST API for Dama stakes (AI), session resume, and profile history."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.current_user import get_current_user
from app.dama import ai_session
from app.dama import wallet as dama_wallet
from app.models.user import User

router = APIRouter(prefix="/dama", tags=["dama"])


class StakeBody(BaseModel):
    stake: str = Field(..., examples=["5", "10", "15", "25"])


class AiFinishBody(BaseModel):
    game_code: str
    outcome: str = Field(..., pattern="^(win|loss|draw)$")


class AiSyncBody(BaseModel):
    game_code: str
    board: list[Any]
    turn: str
    ply_count: int = 0
    quiet_plies: int = 0
    status: str = "playing"
    winner: str | None = None
    turn_deadline: float | None = None


@router.get("/presets")
def stake_presets():
    return {
        "presets": [str(s) for s in dama_wallet.PRESET_STAKES],
        "min": str(dama_wallet.MIN_STAKE),
        "max": str(dama_wallet.MAX_STAKE),
        "fee_rate": str(dama_wallet.FEE_RATE),
        "turn_timeout_sec": ai_session.TURN_TIMEOUT_SECONDS,
    }


@router.post("/ai/start")
async def start_ai(body: StakeBody, user: User = Depends(get_current_user)):
    uid = str(user.id)
    existing = await ai_session.get_ai_session(uid)
    if existing and existing.get("status") == "playing":
        deadline = existing.get("turn_deadline")
        timed_out = bool(deadline and time.time() >= float(deadline))
        if timed_out:
            # Side to move lost on time while the player was away.
            turn = existing.get("turn") or "red"
            outcome = "loss" if turn == "red" else "win"
            try:
                await asyncio.to_thread(
                    dama_wallet.finish_ai_game, uid, existing["game_code"], outcome
                )
            except ValueError:
                pass
            await ai_session.clear_ai_session(uid)
        else:
            # Do not charge again — return the live mid-game session.
            balance = await asyncio.to_thread(dama_wallet.get_balance, uid)
            return {
                "game_code": existing["game_code"],
                "stake": existing["stake"],
                "pot": existing["pot"],
                "system_fee": existing["system_fee"],
                "prize_pool": existing["prize_pool"],
                "balance": balance or "0",
                "turn_deadline": existing.get("turn_deadline"),
                "session": existing,
                "resumed": True,
            }

    try:
        result = await asyncio.to_thread(
            dama_wallet.start_ai_game, uid, body.stake
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = ai_session.new_ai_session(
        game_code=result["game_code"],
        stake=result["stake"],
        pot=result["pot"],
        system_fee=result["system_fee"],
        prize_pool=result["prize_pool"],
    )
    await ai_session.save_ai_session(uid, session)
    result["turn_deadline"] = session["turn_deadline"]
    result["session"] = session
    result["resumed"] = False
    return result


@router.get("/ai/active")
async def active_ai(user: User = Depends(get_current_user)):
    uid = str(user.id)
    session = await ai_session.get_ai_session(uid)
    if not session or session.get("status") != "playing":
        return {"active": False}

    deadline = session.get("turn_deadline")
    if deadline and time.time() >= float(deadline):
        turn = session.get("turn") or "red"
        outcome = "loss" if turn == "red" else "win"
        try:
            settled = await asyncio.to_thread(
                dama_wallet.finish_ai_game, uid, session["game_code"], outcome
            )
        except ValueError:
            settled = None
        await ai_session.clear_ai_session(uid)
        return {
            "active": False,
            "timed_out": True,
            "timeout_outcome": outcome,
            "settled": settled,
        }

    return {"active": True, "session": session}


@router.post("/ai/sync")
async def sync_ai(body: AiSyncBody, user: User = Depends(get_current_user)):
    existing = await ai_session.get_ai_session(str(user.id))
    if not existing or existing.get("game_code") != body.game_code:
        raise HTTPException(status_code=404, detail="No active AI session")
    if existing.get("status") != "playing":
        raise HTTPException(status_code=400, detail="Session already finished")

    deadline = body.turn_deadline
    if deadline is None:
        deadline = time.time() + ai_session.TURN_TIMEOUT_SECONDS

    existing.update(
        {
            "board": body.board,
            "turn": body.turn,
            "ply_count": body.ply_count,
            "quiet_plies": body.quiet_plies,
            "status": body.status,
            "winner": body.winner,
            "turn_deadline": deadline,
        }
    )
    await ai_session.save_ai_session(str(user.id), existing)
    return {"ok": True, "turn_deadline": deadline}


@router.post("/ai/finish")
async def finish_ai(body: AiFinishBody, user: User = Depends(get_current_user)):
    try:
        result = await asyncio.to_thread(
            dama_wallet.finish_ai_game, str(user.id), body.game_code, body.outcome
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await ai_session.clear_ai_session(str(user.id))
    return result


@router.get("/history")
def history(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    return dama_wallet.get_user_history(str(user.id), limit=limit, offset=offset)
