from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal

from app.schemas.user import UserCreate, UserRead
from app.schemas.wallet import WalletAction
from app.models.user import User
from app.models.transaction import Transaction
from app.core.security import hash_password, verify_password, create_access_token
from app.deps import get_db, get_current_user, admin_required
from app.models.transaction import Transaction

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

    # Record transaction
    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=payload.amount,
        status="completed",
        reference=f"ADMIN:{admin.email}"
    )
    db.add(tx)
    db.commit()
    db.refresh(user)

    return {"message": "Deposit successful", "user_id": user.id, "new_balance": user.balance}

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
        status="completed",
        reference=f"ADMIN:{admin.email}"
    )
    db.add(tx)
    db.commit()
    db.refresh(user)

    return {"message": "Withdraw successful", "user_id": user.id, "new_balance": user.balance}

from app.models.transaction import Transaction

@router.get("/transactions")
def get_my_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).order_by(Transaction.created_at.desc()).all()
    return [
        {
            "type": t.type,
            "amount": float(t.amount),
            "reason": t.reason,
            "created_at": t.created_at,
        }
        for t in txns
    ]
