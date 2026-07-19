from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.admin import admin_mgmt, data_retention, payment_accounts, service, user_deletion
from app.admin.helpers import (
    admin_permissions,
    date_range,
    require_admin,
    require_super_admin,
)
from app.admin.schemas import (
    AdminUsernameIn,
    BalanceAdjustmentIn,
    BingoBotUpdateIn,
    BroadcastIn,
    DataRetentionPurgeIn,
    DecisionIn,
    DeleteAllUsersIn,
    DeleteUserIn,
    LottoBotUpdateIn,
    PaymentAccountCreateIn,
    PaymentAccountUpdateIn,
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
def admin_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    caps = admin_permissions(current_user, db)
    permission_list = []
    if caps["is_admin"]:
        permission_list = [
            "dashboard:read",
            "users:read",
            "payments:review",
            "games:read",
            "audit:read",
            "broadcast:send",
            "admins:read",
        ]
        if caps["can_adjust_balance"]:
            permission_list.append("wallet:adjust")
        if caps["can_maintenance"]:
            permission_list.append("data:purge")
        if caps["can_manage_admins"]:
            permission_list.append("admins:write")
    return {
        "is_admin": caps["is_admin"],
        "is_super": caps["is_super"],
        "username": current_user.username,
        "permissions": {
            **caps,
            "list": permission_list,
        },
        # Flat aliases for clients that prefer a single object shape.
        "can_maintenance": caps["can_maintenance"],
        "can_adjust_balance": caps["can_adjust_balance"],
        "can_manage_admins": caps["can_manage_admins"],
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
    admin: User = Depends(require_super_admin),
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
        "paid_from_account_id": (
            str(row.paid_from_account_id) if row.paid_from_account_id else None
        ),
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
        db,
        admin,
        withdrawal_id,
        True,
        payload.reason,
        payload.request_id,
        paid_from_account_id=payload.paid_from_account_id,
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
    payload: BingoBotUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await service.update_bingo_bot(
        db,
        admin,
        enabled=payload.enabled,
        reserve_min=payload.reserve_min,
        reserve_max=payload.reserve_max,
        reserve_count=payload.reserve_count,
        request_id=payload.request_id,
    )


@router.get("/lotto-bot")
async def get_lotto_bot(
    _: User = Depends(require_admin),
):
    return await service.lotto_bot_status()


@router.post("/lotto-bot")
async def set_lotto_bot(
    payload: LottoBotUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await service.update_lotto_bot(
        db,
        admin,
        enabled=payload.enabled,
        reserve_min=payload.reserve_min,
        reserve_max=payload.reserve_max,
        request_id=payload.request_id,
    )


@router.post("/broadcast")
async def send_broadcast(
    payload: BroadcastIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await admin_mgmt.broadcast_message(
        db,
        admin,
        message=payload.message,
        button_url=payload.button_url,
        button_label=payload.button_label,
        game=payload.game,
        request_id=payload.request_id,
    )


@router.get("/payment-accounts")
def get_payment_accounts(
    kind: str | None = Query(None, pattern="^(deposit|withdraw)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return payment_accounts.list_accounts(db, kind=kind)


@router.post("/payment-accounts")
def create_payment_account(
    payload: PaymentAccountCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return payment_accounts.create_account(
        db,
        admin,
        kind=payload.kind,
        bank=payload.bank,
        account_name=payload.account_name,
        account_number=payload.account_number,
        is_enabled=payload.is_enabled,
        sort_order=payload.sort_order,
        request_id=payload.request_id,
    )


@router.patch("/payment-accounts/{account_id}")
def patch_payment_account(
    account_id: uuid.UUID,
    payload: PaymentAccountUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return payment_accounts.update_account(
        db,
        admin,
        account_id,
        bank=payload.bank,
        account_name=payload.account_name,
        account_number=payload.account_number,
        is_enabled=payload.is_enabled,
        sort_order=payload.sort_order,
        request_id=payload.request_id,
    )


@router.delete("/payment-accounts/{account_id}")
def delete_payment_account(
    account_id: uuid.UUID,
    request_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return payment_accounts.delete_account(db, admin, account_id, request_id)


@router.get("/admins")
def get_admins(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return admin_mgmt.list_admins(db)


@router.post("/admins")
def create_admin(
    payload: AdminUsernameIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    return admin_mgmt.add_admin(db, admin, payload.username, payload.request_id)


@router.delete("/admins/{username}")
def delete_admin(
    username: str,
    request_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    return admin_mgmt.remove_admin(db, admin, username, request_id)


@router.get("/data-retention/preview")
def preview_data_retention(
    option: RetentionOption = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return data_retention.preview_purge(db, option)


@router.post("/data-retention/purge")
async def purge_data_retention(
    payload: DataRetentionPurgeIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    return await data_retention.run_purge(
        db,
        admin,
        option=payload.option,
        confirmation=payload.confirmation,
        reason=payload.reason,
        request_id=payload.request_id,
    )


@router.post("/users/delete")
def delete_user(
    payload: DeleteUserIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    return user_deletion.delete_user_by_query(
        db,
        admin,
        query=payload.query,
        confirmation=payload.confirmation,
        reason=payload.reason,
        request_id=payload.request_id,
        force=payload.force,
    )


@router.post("/users/delete-all")
def delete_all_users(
    payload: DeleteAllUsersIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    return user_deletion.delete_all_non_protected_users(
        db,
        admin,
        confirmation=payload.confirmation,
        reason=payload.reason,
        request_id=payload.request_id,
        force=payload.force,
    )
