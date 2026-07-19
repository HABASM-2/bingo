from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # House withdraw account used to pay the user (approve only).
    paid_from_account_id: uuid.UUID | None = None

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class PaymentAccountCreateIn(BaseModel):
    kind: Literal["deposit", "withdraw"]
    bank: str = Field(min_length=1, max_length=80)
    account_name: str = Field(min_length=1, max_length=150)
    account_number: str = Field(min_length=1, max_length=100)
    is_enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)
    request_id: uuid.UUID

    @field_validator("bank", "account_name", "account_number")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class PaymentAccountUpdateIn(BaseModel):
    bank: str | None = Field(default=None, min_length=1, max_length=80)
    account_name: str | None = Field(default=None, min_length=1, max_length=150)
    account_number: str | None = Field(default=None, min_length=1, max_length=100)
    is_enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    request_id: uuid.UUID

    @field_validator("bank", "account_name", "account_number")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def require_change(self) -> "PaymentAccountUpdateIn":
        if all(
            v is None
            for v in (
                self.bank,
                self.account_name,
                self.account_number,
                self.is_enabled,
                self.sort_order,
            )
        ):
            raise ValueError("At least one field must be updated")
        return self


class BingoBotUpdateIn(BaseModel):
    """Toggle and/or set random board reserve range (min–max inclusive).

    Legacy ``reserve_count`` is accepted as min=max for one release.
    """

    enabled: bool | None = None
    reserve_min: int | None = Field(default=None, ge=0, le=50)
    reserve_max: int | None = Field(default=None, ge=0, le=50)
    reserve_count: int | None = Field(default=None, ge=0, le=50)
    request_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "BingoBotUpdateIn":
        if (
            self.reserve_min is not None
            and self.reserve_max is not None
            and self.reserve_min > self.reserve_max
        ):
            raise ValueError("reserve_min must be ≤ reserve_max")
        return self


class LottoBotUpdateIn(BaseModel):
    """Toggle and/or set Lotto house-bot number reserve range (1–25)."""

    enabled: bool | None = None
    reserve_min: int | None = Field(default=None, ge=1, le=25)
    reserve_max: int | None = Field(default=None, ge=1, le=25)
    request_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "LottoBotUpdateIn":
        if (
            self.reserve_min is not None
            and self.reserve_max is not None
            and self.reserve_min > self.reserve_max
        ):
            raise ValueError("reserve_min must be ≤ reserve_max")
        return self


class DataRetentionPurgeIn(BaseModel):
    option: RetentionOption
    confirmation: str = Field(min_length=3, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
    request_id: uuid.UUID

    @field_validator("confirmation", "reason")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class DeleteUserIn(BaseModel):
    """Delete one user by telegram username, telegram id, or UUID."""

    query: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=3, max_length=32)
    reason: str = Field(min_length=3, max_length=500)
    request_id: uuid.UUID
    force: bool = False

    @field_validator("query", "confirmation", "reason")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class DeleteAllUsersIn(BaseModel):
    """Delete all non-admin, non-bot users (extreme)."""

    confirmation: str = Field(min_length=3, max_length=32)
    reason: str = Field(min_length=3, max_length=500)
    request_id: uuid.UUID
    force: bool = False

    @field_validator("confirmation", "reason")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class BroadcastIn(BaseModel):
    """Send a Telegram message to all real users (optional link / game button)."""

    message: str = Field(min_length=1, max_length=4000)
    button_url: str | None = Field(default=None, max_length=2048)
    button_label: str | None = Field(default=None, max_length=64)
    game: str | None = Field(default=None, max_length=32)
    request_id: uuid.UUID

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        return value.strip()

    @field_validator("button_url", "button_label", "game")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_button(self) -> "BroadcastIn":
        if self.button_label and not self.button_url and not self.game:
            raise ValueError("button_label requires button_url or game")
        return self


class AdminUsernameIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    request_id: uuid.UUID

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return value.strip().lstrip("@")

