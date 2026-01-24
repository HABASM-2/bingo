from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.schemas.user import UserCreate, UserRead
from app.schemas.wallet import WalletAction, UserWithdrawRequest
from app.models.user import User
from app.models.transaction import Transaction
from app.core.security import hash_password, verify_password, create_access_token
from app.deps import get_db, get_current_user, admin_required
from app.models.transaction import Transaction
from app.services.wallet import create_withdraw_request

from app.routes.telegram_auth import verify_telegram
from app.routes.telegram_bot import send_message

router = APIRouter(prefix="/auth", tags=["Auth"])

# --- Auth routes ---
@router.post("/register", response_model=UserRead)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login")
def login(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout")
def logout():
    return {"message": "Logout successful. Remove token on client side."}

# --- Manual wallet operations (admin only) ---
@router.post("/deposit")
def manual_deposit(payload: WalletAction, db: Session = Depends(get_db), admin: User = Depends(admin_required)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    # Update balance
    user.balance += payload.amount

    # Record transaction (required stake_amount, reason optional)
    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=payload.amount,
        stake_amount=0,  # admin deposits are not linked to a game
        reason=payload.note or f"Admin deposit by {admin.display_name}"
    )
    db.add(tx)
    db.commit()
    db.refresh(user)

    return {"message": "Deposit successful", "user_id": str(user.id), "new_balance": float(user.balance)}

@router.post("/telegram-login")
def telegram_login(payload: dict, db: Session = Depends(get_db)):
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="No init_data provided")

    valid, data = verify_telegram(init_data)
    if not valid:
        raise HTTPException(status_code=403, detail="Invalid Telegram data")

    telegram_id = int(data["id"])
    username = data.get("username")
    first_name = data.get("first_name")

    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=username,
            telegram_first_name=first_name,
            balance=0.0,
            is_active=True,
            is_admin=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/withdraw")
def manual_withdraw(payload: WalletAction, db: Session = Depends(get_db), admin: User = Depends(admin_required)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if user.balance < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Update balance
    user.balance -= payload.amount

    # Record transaction
    tx = Transaction(
        user_id=user.id,
        type="withdraw",
        amount=payload.amount,
        stake_amount=0,  # admin withdraw not linked to a game
        reason=payload.note or f"Admin withdraw by {admin.display_name}"
    )
    db.add(tx)
    db.commit()
    db.refresh(user)

    return {"message": "Withdraw successful", "user_id": str(user.id), "new_balance": float(user.balance)}

from app.models.transaction import Transaction

@router.get("/transactions")
def get_my_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔥 Limit to 10 most recent transactions
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(10)  # only top 10
        .all()
    )

    return [
        {
            "id": str(t.id),
            "type": t.type,
            "amount": float(t.amount),
            "reason": t.reason,
            "created_at": t.created_at,
            "withdraw_status": t.withdraw_status if t.type == "withdraw" else None
        }
        for t in txns
    ]

@router.post("/withdraw/request")
def request_withdraw(
    payload: UserWithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if current_user.balance < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Lock funds
    tx = create_withdraw_request(
        current_user,
        payload.amount,
        db,
        payload.note or "User withdraw request"
    )

    return {
        "message": "Withdraw request submitted",
        "status": tx.withdraw_status,
        "transaction": str(tx.id)
    }

@router.post("/withdraw/cancel/{tx_id}")
def cancel_withdraw(
    tx_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id,
        Transaction.user_id == current_user.id,
        Transaction.type == "withdraw"
    ).first()

    if not tx:
        raise HTTPException(status_code=404, detail="Withdraw not found")

    if tx.withdraw_status != "pending":
        raise HTTPException(status_code=400, detail="Cannot cancel at this stage")

    # Return locked funds
    current_user.balance += tx.amount
    tx.withdraw_status = "cancelled"

    db.commit()
    return {"message": "Withdraw cancelled"}

@router.get("/admin/withdraws")
def get_withdraws(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get paginated withdraws for admin view.
    Includes user telegram_username and telegram_first_name.
    """
    # Join Transaction with User table
    query = (
        db.query(Transaction, User)
        .join(User, Transaction.user_id == User.id)
        .filter(Transaction.type == "withdraw")
        .order_by(Transaction.created_at.desc())
    )

    total = query.count()
    txs = query.offset(skip).limit(limit).all()

    result = []
    for tx, user in txs:
        row = {
            "id": str(tx.id),
            "user_id": str(tx.user_id),
            "username": user.telegram_username,
            "first_name": user.telegram_first_name,
            "amount": float(tx.amount),
            "status": tx.withdraw_status,
            "date": tx.created_at,
        }
        if hasattr(tx, "bank") and tx.bank:
            row["bank"] = tx.bank
        if hasattr(tx, "account_number") and tx.account_number:
            row["account_number"] = tx.account_number
        result.append(row)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "withdraws": result
    }

@router.post("/withdraw/update/{tx_id}")
async def update_withdraw_status(
    tx_id: str,
    status: str,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Admin endpoint to mark a user withdraw as 'completed' or 'rejected'.
    Sends Telegram notification to the user.
    """
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Withdraw transaction not found")

    if tx.type != "withdraw":
        raise HTTPException(status_code=400, detail="Transaction is not a withdraw")

    if tx.withdraw_status in ["completed", "rejected", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Transaction already {tx.withdraw_status}")

    if status not in ["completed", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'completed' or 'rejected'")

    user = db.query(User).filter(User.id == tx.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Handle rejected: refund user
    if status == "rejected":
        user.balance += tx.amount
        tx.reason = (tx.reason or "") + " | Rejected by admin"

    # Update status
    tx.withdraw_status = status
    db.commit()
    db.refresh(tx)

    # --- Telegram notification ---
    if user.telegram_id:
        try:
            text = (
                f"💸 Your withdrawal of ${tx.amount:.2f} has been {status}.\n"
                f"Current balance: ${user.balance:.2f}"
            )
            await send_message(user.telegram_id, text)
        except Exception as e:
            print("Failed to send Telegram message:", e)

    return {
        "message": f"Withdraw transaction {tx_id} marked as '{status}'",
        "user_id": str(tx.user_id),
        "amount": float(tx.amount),
        "status": tx.withdraw_status
    }

@router.post("/admin/withdraw/update/{tx_id}")
async def admin_update_withdraw_status(
    tx_id: str,
    status: str,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
):
    """
    Admin endpoint to update user withdraw status and notify via Telegram.
    """
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Withdraw transaction not found")

    if tx.type != "withdraw":
        raise HTTPException(status_code=400, detail="Transaction is not a withdraw")

    if tx.withdraw_status in ["completed", "rejected", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Transaction already {tx.withdraw_status}")

    if status not in ["processing", "completed", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'completed' or 'rejected'")

    user = db.query(User).filter(User.id == tx.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Refund if rejected
    if status == "rejected":
        user.balance += tx.amount
        tx.reason = (tx.reason or "") + " | Rejected by admin"

    # Update status
    tx.withdraw_status = status
    db.commit()
    db.refresh(tx)

    # Telegram notification
    if user.telegram_id:
        try:
            await send_message(
                user.telegram_id,
                f"💸 Your withdrawal of ${tx.amount:.2f} has been {status}.\nCurrent balance: ${user.balance:.2f}"
            )
        except Exception as e:
            print("Failed to send Telegram message:", e)

    return {
        "message": f"Withdraw transaction {tx_id} marked as '{status}'",
        "user_id": str(tx.user_id),
        "amount": float(tx.amount),
        "status": tx.withdraw_status
    }