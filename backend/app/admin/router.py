from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.admin import data_retention, service
from app.admin.helpers import date_range, is_admin, require_admin
from app.admin.schemas import (
    BalanceAdjustmentIn,
    BingoBotToggleIn,
    DataRetentionPurgeIn,
    DecisionIn,
    RetentionOption,
)
from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.bot.notify import notify_withdrawal_decision
from app.models.request_tr import WithdrawRequest
from app.models.user import User

logger = logging.getLogger("app.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])


def _queue_withdrawal_notify(background_tasks: BackgroundTasks, result: dict) -> dict:
    notify = result.get("notify")
    if result.get("idempotent") or not notify:
        return {k: v for k, v in result.items() if k != "notify"}

    async def _send() -> None:
        try:
            await notify_withdrawal_decision(
                telegram_id=notify["telegram_id"],
                language_code=notify.get("language_code"),
                approved=bool(notify.get("approved")),
                amount=notify["amount"],
                withdrawal_id=notify["withdrawal_id"],
                balance=notify.get("balance"),
                reason=notify.get("reason"),
            )
        except Exception:
            logger.exception(
                "Withdrawal notify task failed withdrawal_id=%s",
                notify.get("withdrawal_id"),
            )

    background_tasks.add_task(_send)
    return {k: v for k, v in result.items() if k != "notify"}


@router.get("/me")
def admin_me(current_user: User = Depends(get_current_user)):
    allowed = is_admin(current_user)
    return {
        "is_admin": allowed,
        "username": current_user.username,
        "permissions": (
            ["dashboard:read", "users:read", "wallet:adjust", "payments:review",
             "games:read", "audit:read", "data:purge"]
            if allowed else []
        ),
    }


@router.get("/dashboard")
def get_dashboard(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    start, end = date_range(from_, to)
    return service.dashboard(db, start, end)


@router.get("/games/summary")
def get_games_summary(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    start, end = date_range(from_, to)
    return service.game_summary(db, start, end)


@router.get("/games/{game}/players")
def get_game_players(
    game: str,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    start, end = date_range(from_, to)
    return service.game_players(db, game.casefold(), start, end, limit, offset)


@router.get("/users")
def get_users(
    search: str | None = Query(None, max_length=100),
    status: str | None = Query(None, pattern="^(active|inactive|bot)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("joined_desc"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.list_users(db, search, status, limit, offset, sort)


@router.get("/users/{user_id}")
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.user_detail(db, user_id)


@router.post("/users/{user_id}/balance-adjustments")
def adjust_user_balance(
    user_id: uuid.UUID,
    payload: BalanceAdjustmentIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return service.adjust_balance(
        db, admin, user_id, payload.amount, payload.reason, payload.request_id
    )


@router.get("/deposits")
def get_deposits(
    status: str | None = Query("all"),
    search: str | None = Query(None, max_length=100),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    start = end = None
    if from_ is not None or to is not None:
        start, end = date_range(from_, to)
    return service.list_deposits(
        db, status, limit, offset, search=search, start=start, end=end,
    )


@router.get("/withdrawals")
def get_withdrawals(
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.list_withdrawals(db, status, limit, offset)


@router.get("/withdrawals/{withdrawal_id}")
def get_withdrawal(
    withdrawal_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = db.query(WithdrawRequest).filter(WithdrawRequest.id == withdrawal_id).first()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    return {
        "id": str(row.id), "user_id": str(row.user_id), "method": row.method,
        "account_name": row.account_name, "account_number": row.account_number,
        "amount": service.money(row.amount), "fee": service.money(row.fee),
        "status": row.status, "created_at": row.created_at,
        "processed_at": row.processed_at,
    }


@router.post("/withdrawals/{withdrawal_id}/approve")
def approve_withdrawal(
    withdrawal_id: uuid.UUID,
    payload: DecisionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = service.decide_withdrawal(
        db, admin, withdrawal_id, True, payload.reason, payload.request_id
    )
    return _queue_withdrawal_notify(background_tasks, result)


@router.post("/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(
    withdrawal_id: uuid.UUID,
    payload: DecisionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not payload.reason:
        raise HTTPException(422, "A rejection reason is required")
    result = service.decide_withdrawal(
        db, admin, withdrawal_id, False, payload.reason, payload.request_id
    )
    return _queue_withdrawal_notify(background_tasks, result)


@router.get("/audit")
@router.get("/activity")
def get_audit(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.audit_feed(db, limit, offset)


@router.get("/bingo-bot")
async def get_bingo_bot(
    _: User = Depends(require_admin),
):
    return await service.bingo_bot_status()


@router.post("/bingo-bot")
async def set_bingo_bot(
    payload: BingoBotToggleIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await service.set_bingo_bot_enabled(
        db, admin, payload.enabled, payload.request_id
    )


@router.get("/data-retention/preview")
def preview_data_retention(
    option: RetentionOption = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return data_retention.preview_purge(db, option)


@router.post("/data-retention/purge")
async def purge_data_retention(
    payload: DataRetentionPurgeIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await data_retention.run_purge(
        db,
        admin,
        option=payload.option,
        confirmation=payload.confirmation,
        reason=payload.reason,
        request_id=payload.request_id,
    )
