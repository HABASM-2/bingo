from pydantic import BaseModel
from uuid import UUID
from decimal import Decimal
from datetime import datetime

class TransactionBase(BaseModel):
    amount: Decimal

class DepositCreate(TransactionBase):
    pass

class WithdrawCreate(TransactionBase):
    pass

class TransactionRead(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    amount: Decimal
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
