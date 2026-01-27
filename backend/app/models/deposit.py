# app/models/deposit.py
import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base

class IncomingDeposit(Base):
    __tablename__ = "incoming_deposits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider = Column(String)  # telebirr / cbe / abyssinia
    sender = Column(String)    # phone or masked account
    amount = Column(Numeric(12,2))
    transaction_id = Column(String, unique=True, index=True)

    raw_text = Column(String)

    is_matched = Column(Boolean, default=False)
    matched_user_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
