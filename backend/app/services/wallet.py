from sqlalchemy.orm import Session
from decimal import Decimal
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