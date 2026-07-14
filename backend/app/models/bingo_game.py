import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BingoGame(Base):
    """One finished (or in-progress) Bingo round, persisted for history.

    A row is written the moment a round starts (stakes charged, cartelas
    dealt) so ``game_code`` is durable for tracking, then updated to
    ``finished`` with the winning metadata when the round settles.
    """

    __tablename__ = "bingo_games"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-facing round id shown in the UI (e.g. "MB7K3Q90"), unique per round.
    game_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )

    room_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="in_progress",
    )

    board_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    # Total staked boards in the round (one user with 2 cards counts as 2).
    total_boards: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Unique paying users in the round.
    total_players: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Locked prize pool = total_boards * board_price.
    derash: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    winning_pattern: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    winner_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    results: Mapped[list["BingoGameResult"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class BingoGameResult(Base):
    """Per-user participation in a round: how many boards they staked, how
    much they paid, and (if they won) how much of the derash they took."""

    __tablename__ = "bingo_game_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bingo_games.id", ondelete="CASCADE"),
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    boards_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    stake_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    is_winner: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    amount_won: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    game: Mapped["BingoGame"] = relationship(
        back_populates="results",
    )
