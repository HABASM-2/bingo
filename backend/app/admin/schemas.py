from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class BalanceAdjustmentIn(BaseModel):
    amount: Decimal = Field(decimal_places=2, max_digits=12)
    reason: str = Field(min_length=3, max_length=500)
    request_id: uuid.UUID

    @field_validator("amount")
    @classmethod
    def non_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Amount must not be zero")
        return value.quantize(Decimal("0.01"))

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        return value.strip()


class DecisionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    request_id: uuid.UUID

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else None
