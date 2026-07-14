from datetime import datetime
import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    ForeignKey,
    Numeric,
    DateTime,
    func,
)

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    func,
)

from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SMSTransaction(Base):

    __tablename__ = "sms_transactions"


    id: Mapped[int] = mapped_column(
        primary_key=True,
    )


    transaction_id = mapped_column(
        String(100),
        unique=True,
        index=True
    )


    amount = mapped_column(
        Numeric(12,2)
    )


    source = mapped_column(
        String(50)
    )


    transaction_type = mapped_column(
        String(30)
    )


    sender = mapped_column(
        String(120),
        nullable=True
    )


    is_used = mapped_column(
        Boolean,
        default=False
    )


    used_at = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    inviter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    invited_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        unique=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )