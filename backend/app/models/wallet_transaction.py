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


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

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

    transaction_type: Mapped[str] = mapped_column(
        String(30),
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    balance_before: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="COMPLETED",
    )

    reference_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

class Deposit(Base):

    __tablename__ = "deposits"


    id: Mapped[int] = mapped_column(
        primary_key=True
    )


    user_id = mapped_column(
        ForeignKey("users.id")
    )


    amount = mapped_column(
        Numeric(12,2)
    )


    method = mapped_column(
        String(30)
    )


    sms_transaction_id = mapped_column(
        String(60),
        unique=True
    )


    created_at = mapped_column(
        DateTime,
        server_default=func.now()
    )