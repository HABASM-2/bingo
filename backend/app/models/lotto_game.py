"""Persistent, server-authoritative Lotto Spin state."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class LottoRound(Base):
    __tablename__ = "lotto_rounds"
    __table_args__ = (
        CheckConstraint("room_stake IN (10, 25, 50, 100)", name="ck_lotto_round_stake"),
        CheckConstraint(
            "status IN ('open', 'countdown', 'drawing', 'completed', 'cancelled')",
            name="ck_lotto_round_status",
        ),
        CheckConstraint("capacity IN (20, 25)", name="ck_lotto_round_capacity"),
        Index("ix_lotto_rounds_stake_created", "room_stake", "created_at"),
        Index(
            "uq_lotto_round_active_stake",
            "room_stake",
            unique=True,
            postgresql_where=text("status IN ('open', 'countdown', 'drawing')"),
            sqlite_where=text("status IN ('open', 'countdown', 'drawing')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    room_stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    round_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    total_pool: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    first_prize: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    second_prize: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    third_prize: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reserve_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    countdown_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    draw_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    drawing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    reservations: Mapped[list["LottoReservation"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )
    winners: Mapped[list["LottoWinner"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class LottoReservation(Base):
    __tablename__ = "lotto_reservations"
    __table_args__ = (
        UniqueConstraint("round_id", "number", name="uq_lotto_reservation_number"),
        CheckConstraint("number BETWEEN 1 AND 25", name="ck_lotto_reservation_number"),
        Index("ix_lotto_reservation_round_user", "round_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lotto_rounds.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    round: Mapped[LottoRound] = relationship(back_populates="reservations")


class LottoReservationRequest(Base):
    __tablename__ = "lotto_reservation_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_lotto_request_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotto_rounds.id"), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    numbers_csv: Mapped[str] = mapped_column(String(80), nullable=False)
    charged_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    wallet_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LottoWinner(Base):
    __tablename__ = "lotto_winners"
    __table_args__ = (
        UniqueConstraint("round_id", "rank", name="uq_lotto_winner_rank"),
        UniqueConstraint("round_id", "number", name="uq_lotto_winner_number"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_lotto_winner_rank"),
        CheckConstraint("number BETWEEN 1 AND 25", name="ck_lotto_winner_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lotto_rounds.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    prize: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payout_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    round: Mapped[LottoRound] = relationship(back_populates="winners")
