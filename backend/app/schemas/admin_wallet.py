from pydantic import BaseModel
from decimal import Decimal
from uuid import UUID

class AdminWalletAction(BaseModel):
    user_id: UUID
    amount: Decimal
    note: str | None = None
