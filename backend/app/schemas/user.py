from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import Optional

class UserBase(BaseModel):
    email: Optional[EmailStr] = None

class UserCreate(UserBase):
    password: str

class UserRead(BaseModel):
    id: UUID

    email: Optional[EmailStr] = None

    # 🔥 Telegram fields
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    telegram_first_name: Optional[str] = None

    balance: float
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True