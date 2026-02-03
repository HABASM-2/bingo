from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.models.deposit import IncomingDeposit
from app.models.transaction import Transaction
from app.models.user import User
from app.deps import get_db, admin_required

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/financial-overview")
def financial_overview(db: Session = Depends(get_db), admin: User = Depends(admin_required)):
    """
    Admin financial overview:
    - Deposits: only telebirr, cbe, abyssinia, excluding refunds, stake deposits, etc.
    - Withdraws: only completed, non-stake withdrawals, any bank.
    - Users: total balances currently held
    - Profit: total deposits - total holding + total withdraws (all-time)
      Profit same across periods
    """

    now = datetime.utcnow()
    periods = {
        "today": now - timedelta(days=1),
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
        "year": now - timedelta(days=365),
    }

    # --- Compute total user holdings once ---
    total_holding = float(db.query(func.coalesce(func.sum(User.balance), 0)).scalar() or 0)

    # --- Compute total deposits (all-time) ---
    total_all_deposits = float(
        db.query(func.coalesce(func.sum(IncomingDeposit.amount), 0))
        .filter(IncomingDeposit.provider.in_(["telebirr", "cbe", "abyssinia"]))
        .filter(~IncomingDeposit.raw_text.ilike("%refund%"))
        .filter(~IncomingDeposit.raw_text.ilike("%stake%"))
        .scalar() or 0
    )

    # --- Compute total completed withdrawals (all-time) ---
    total_all_withdraws = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.type == "withdraw")
        .filter(Transaction.stake_amount == 0)
        .filter(Transaction.withdraw_status == "completed")
        .scalar() or 0
    )

    # --- Consistent profit ---
    consistent_profit = total_all_deposits - total_holding - total_all_withdraws

    overview = {}

    for period_name, start_date in periods.items():
        # --- Deposits per period ---
        deposits_query = (
            db.query(
                IncomingDeposit.provider,
                func.coalesce(func.sum(IncomingDeposit.amount), 0)
            )
            .filter(IncomingDeposit.created_at >= start_date)
            .filter(IncomingDeposit.provider.in_(["telebirr", "cbe", "abyssinia"]))
            .filter(~IncomingDeposit.raw_text.ilike("%refund%"))  # exclude refunds
            .filter(~IncomingDeposit.raw_text.ilike("%stake%"))   # exclude stakes
            .group_by(IncomingDeposit.provider)
            .all()
        )
        deposits = {dep[0]: float(dep[1]) for dep in deposits_query}
        total_deposits = sum(deposits.values())

        # --- Withdraws per period ---
        withdraws_query = (
            db.query(
                Transaction.bank,
                func.coalesce(func.sum(Transaction.amount), 0)
            )
            .filter(Transaction.type == "withdraw")
            .filter(Transaction.stake_amount == 0)
            .filter(Transaction.withdraw_status == "completed")
            .filter(Transaction.created_at >= start_date)
            .group_by(Transaction.bank)
            .all()
        )
        withdraws = {w[0] or "Unknown": float(w[1]) for w in withdraws_query}
        total_withdraws = sum(withdraws.values())

        overview[period_name] = {
            "deposits": deposits,
            "total_deposits": total_deposits,
            "withdraws": withdraws,
            "total_withdraws": total_withdraws,
            "total_users_holding": total_holding,
            "profit": consistent_profit,  # same across periods
        }

    return overview
