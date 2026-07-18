import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(32),
        unique=True,
        nullable=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(128),
    )

    last_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    language_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    photo_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
        nullable=False,
    )

    referral_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )

    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    is_premium: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    # System / house participants (e.g. Bingo autofill bot). Not Telegram users.
    is_bot: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    referred_by: Mapped["User | None"] = relationship(
        remote_side=[id],
    )