from sqlalchemy.orm import Session
from decimal import Decimal
from fastapi import HTTPException
from app.models.transaction import Transaction
from app.models.user import User

def deposit(db: Session, user: User, amount: Decimal):
    if amount <= 0:
        raise ValueError("Invalid deposit amount")

    user.balance += amount

    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=amount,
        status="completed"
    )

    db.add(tx)
    db.commit()
    db.refresh(user)

    return tx

def withdraw(db: Session, user: User, amount: Decimal):
    if amount <= 0:
        raise ValueError("Invalid withdrawal amount")

    if user.balance < amount:
        raise ValueError("Insufficient balance")

    user.balance -= amount

    tx = Transaction(
        user_id=user.id,
        type="withdraw",
        amount=amount,
        status="completed"
    )

    db.add(tx)
    db.commit()
    db.refresh(user)

    return tx

def create_withdraw_request(user: User, amount: Decimal, db: Session, source: str = "app"):
    # Block if already pending
    existing = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.type == "withdraw",
        Transaction.withdraw_status == "pending"
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending withdrawal")

    if user.balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Lock funds
    user.balance -= amount

    tx = Transaction(
        user_id=user.id,
        type="withdraw",
        amount=amount,
        stake_amount=0,
        reason=f"Withdraw via {source}",
        withdraw_status="pending"
    )

    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx