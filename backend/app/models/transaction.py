# app/models/transaction.py
import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy import Enum
import enum

class WithdrawStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"   # user cancelled


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    type = Column(String, nullable=False)  # deposit | withdraw
    amount = Column(Numeric(12, 2), nullable=False)
    stake_amount = Column(Numeric(12, 2), nullable=False)
    game_no = Column(String, nullable=True)
    reason = Column(String, default="")

    # 🔥 NEW
    withdraw_status = Column(
        Enum(WithdrawStatus),
        default=WithdrawStatus.PENDING,
        nullable=True
    )

    # --- Optional bank info for real withdrawals ---
    bank = Column(String, nullable=True)            # e.g., "CBE", "Telebirr", "Abyssinia"
    account_number = Column(String, nullable=True)  # user account number

    created_at = Column(DateTime(timezone=True), server_default=func.now())