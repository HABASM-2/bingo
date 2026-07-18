from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RetentionOption = Literal[
    "all",
    "games_only",
    "7d",
    "14d",
    "21d",
    "30d",
    "60d",
    "90d",
    "120d",
    "150d",
]


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


class BingoBotToggleIn(BaseModel):
    enabled: bool
    request_id: uuid.UUID | None = None


class DataRetentionPurgeIn(BaseModel):
    option: RetentionOption
    confirmation: str = Field(min_length=3, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
    request_id: uuid.UUID

    @field_validator("confirmation", "reason")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()
