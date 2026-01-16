from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    balance: float
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True