"""Persisted Dama matches for wallet settlement and profile history."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DamaGame(Base):
    __tablename__ = "dama_games"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    game_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # ai | online
    mode: Mapped[str] = mapped_column(String(20), default="online", nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)

    stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    pot: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    system_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    prize_pool: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Redis match id for online; same as game_code key for AI sessions.
    match_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    winner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # red | black | draw | null
    winner_side: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list[DamaGameResult]] = relationship(
        "DamaGameResult",
        back_populates="game",
        cascade="all, delete-orphan",
    )


class DamaGameResult(Base):
    __tablename__ = "dama_game_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dama_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    stake_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amount_won: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # win | loss | draw
    outcome: Mapped[str] = mapped_column(String(10), default="loss", nullable=False)

    game: Mapped[DamaGame] = relationship("DamaGame", back_populates="results")
