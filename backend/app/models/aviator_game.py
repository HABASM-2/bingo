"""Persisted Aviator rounds and per-player bets."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AviatorRound(Base):
    __tablename__ = "aviator_rounds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    round_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="betting", nullable=False)
    crash_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    player_count: Mapped[int] = mapped_column(default=0, nullable=False)
    total_stake: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_payout: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    system_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    max_payout_mult: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1.4, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bets: Mapped[list[AviatorBet]] = relationship(
        "AviatorBet",
        back_populates="round",
        cascade="all, delete-orphan",
    )


class AviatorBet(Base):
    __tablename__ = "aviator_bets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aviator_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(80), default="Player", nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cashout_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    amount_won: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    # pending | won | lost
    outcome: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    slot: Mapped[int] = mapped_column(default=0, nullable=False)

    round: Mapped[AviatorRound] = relationship("AviatorRound", back_populates="bets")
