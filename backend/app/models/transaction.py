# app/models/transaction.py
import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    type = Column(String, nullable=False)  # "deposit" | "withdraw"

    amount = Column(Numeric(12, 2), nullable=False)

    # 🔥 NEW
    stake_amount = Column(Numeric(12, 2), nullable=False)

    # 🔥 OPTIONAL BUT RECOMMENDED
    game_no = Column(String, nullable=True)

    reason = Column(String, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
