from sqlalchemy import Column, String, Boolean, DateTime, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base

class User(Base):
    __tablename__ = "users"

    # id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # email = Column(String, unique=True, index=True, nullable=False)
    # hashed_password = Column(String, nullable=False)
    # is_active = Column(Boolean, default=True)
    # is_admin = Column(Boolean, default=False)          # <--- admin flag
    # balance = Column(Numeric(12, 2), default=0.0)     # <--- user balance
    # created_at = Column(DateTime(timezone=True), server_default=func.now())

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 🔥 NEW TELEGRAM FIELDS
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True)
    telegram_username = Column(String, nullable=True)
    telegram_first_name = Column(String, nullable=True)

    email = Column(String, unique=True, index=True, nullable=True)  # make optional
    hashed_password = Column(String, nullable=True)  # not needed for telegram users

    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    balance = Column(Numeric(12, 2), default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def display_name(self) -> str:
        if self.telegram_username:
            return f"@{self.telegram_username}"
        if self.telegram_first_name:
            return self.telegram_first_name
        if self.email:
            return self.email
        return "Player"
