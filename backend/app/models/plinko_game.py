"""Server-authoritative Plinko plays."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PlinkoPlay(Base):
    __tablename__ = "plinko_plays"
    __table_args__ = (
        Index("ix_plinko_plays_user_created", "user_id", "created_at"),
    )

    # The client supplies this UUID as an idempotency key.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    risk: Mapped[str] = mapped_column(String(10), nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_result: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
