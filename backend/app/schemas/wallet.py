from pydantic import BaseModel
from uuid import UUID
from decimal import Decimal

class WalletAction(BaseModel):
    user_id: UUID
    amount: Decimal
    note: str | None = None  # optional admin note
