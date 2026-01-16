from sqlalchemy import Column, String, Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)          # <--- admin flag
    balance = Column(Numeric(12, 2), default=0.0)     # <--- user balance
    created_at = Column(DateTime(timezone=True), server_default=func.now())
