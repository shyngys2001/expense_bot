import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AutoPairRequest(BaseModel):
    from_date: dt.date = Field(alias="from")
    to_date: dt.date = Field(alias="to")
    window_days: int = Field(default=1, ge=0, le=7)
    tolerance: Decimal = Field(default=Decimal("0"), ge=0)
    threshold: int = Field(default=80, ge=0, le=100)
    account_ids: list[int] | None = None


class AutoPairResponse(BaseModel):
    paired: int
    reviewed_candidates: int


class TransferPairTransaction(BaseModel):
    transaction_id: int
    account_id: int
    account_name: str
    tx_date: dt.date
    signed_amount: Decimal
    currency: str
    description: str


class TransferPairRead(BaseModel):
    transfer_pair_id: UUID
    confidence: int
    left: TransferPairTransaction
    right: TransferPairTransaction
