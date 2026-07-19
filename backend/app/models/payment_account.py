"""House bank accounts for deposits (shown to users) and withdrawals (admin payout sources)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PaymentAccount(Base):
    """Receiving (deposit) or house payout-source (withdraw) bank account."""

    __tablename__ = "payment_accounts"
    __table_args__ = (
        UniqueConstraint(
            "kind", "bank", "account_number",
            name="uq_payment_accounts_kind_bank_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    bank: Mapped[str] = mapped_column(String(80), nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
