import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DepositRequest(Base):
    __tablename__ = "deposit_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    sms_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("sms_transactions.id"),
        nullable=True,
    )

    method: Mapped[str] = mapped_column(
        String(30),
    )

    transaction_id: Mapped[str | None] = mapped_column(
        String(60),
        unique=True,
        nullable=True,
    )

    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="WAITING_SMS",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    method: Mapped[str] = mapped_column(
        String(30),
    )

    account_name: Mapped[str] = mapped_column(
        String(150),
    )

    account_number: Mapped[str] = mapped_column(
        String(100),
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class TransferRequest(Base):
    __tablename__ = "transfer_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="COMPLETED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )