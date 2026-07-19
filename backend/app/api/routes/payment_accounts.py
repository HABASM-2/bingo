"""Public payment-account endpoints (enabled accounts only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin import payment_accounts
from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.models.user import User

router = APIRouter(prefix="/payment-accounts", tags=["payment-accounts"])


@router.get("")
def list_enabled_payment_accounts(
    kind: str = Query(..., pattern="^(deposit|withdraw)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return enabled house accounts for the given kind.

    Deposit: receiving destinations shown to users.
    Withdraw: house payout-source accounts (for clients that need them;
    Mini App does not currently drive withdrawals).
    """
    return payment_accounts.list_enabled_public(db, kind)
