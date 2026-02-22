import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TransactionKind, TransactionSource, TransactionStatus, TransactionType


class QuickAddRequest(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    account_id: int | None = Field(default=None, ge=1)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Текст не может быть пустым")
        return stripped


class TransactionCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="KZT", min_length=3, max_length=3)
    type: TransactionType
    category_id: int | None = None
    account_id: int | None = Field(default=None, ge=1)
    tx_date: dt.date | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Описание не может быть пустым")
        return normalized


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    amount: Decimal
    signed_amount: Decimal
    currency: str
    type: TransactionType
    kind: TransactionKind
    status: TransactionStatus
    account_id: int
    account_name: str
    account_bank: str | None = None
    import_id: int | None = None
    category_id: int
    category_name: str
    category_locked: bool
    transfer_pair_id: UUID | None
    matched_account_id: int | None
    matched_account_name: str | None
    match_confidence: int | None
    source: TransactionSource
    tx_date: dt.date
    posted_at: dt.datetime | None
    created_at: dt.datetime


class TransactionUpdate(BaseModel):
    category_id: int | None = None
    category_locked: bool | None = None
    kind: TransactionKind | None = None


class TransactionDebugRead(BaseModel):
    id: int
    source: TransactionSource
    import_id: int | None
    account_id: int
    raw: dict[str, Any] | None
    external_hash: str | None
    created_at: dt.datetime
