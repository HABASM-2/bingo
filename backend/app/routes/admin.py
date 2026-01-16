from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.deps import get_db, get_current_user
from app.models.user import User
from decimal import Decimal
from app.models.transaction import Transaction

router = APIRouter(prefix="/admin", tags=["Admin"])

# Request body for admin update
class AdminBalanceUpdate(BaseModel):
    user_email: str
    amount: float  # positive = deposit, negative = withdraw
    reason: str = ""

@router.post("/update-balance")
def update_balance(
    data: AdminBalanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Find target user
    target_user = db.query(User).filter(User.email == data.user_email).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert amount to Decimal
    amt = Decimal(str(data.amount))

    # Determine type
    if amt >= 0:
        txn_type = "deposit"
    else:
        txn_type = "withdraw"
        # Optional: prevent negative balance
        if (target_user.balance or Decimal("0")) + amt < 0:
            raise HTTPException(status_code=400, detail="Insufficient balance")

    # Update balance
    target_user.balance = (target_user.balance or Decimal("0")) + amt

    # Record transaction
    txn = Transaction(
        user_id=target_user.id,
        type=txn_type,
        amount=abs(amt),
        reason=data.reason,
    )
    db.add(txn)
    db.commit()
    db.refresh(target_user)

    return {
        "email": target_user.email,
        "new_balance": float(target_user.balance),
        "transaction": {
            "type": txn_type,
            "amount": float(abs(amt)),
            "reason": data.reason,
        },
    }

@router.get("/transactions")
def admin_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    txns = db.query(Transaction).order_by(Transaction.created_at.desc()).all()
    return [
        {
            "user_email": db.query(User).filter(User.id == t.user_id).first().email,
            "type": t.type,
            "amount": float(t.amount),
            "reason": t.reason,
            "created_at": t.created_at,
        }
        for t in txns
    ]