import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


class AccountRead(BaseModel):
    id: int
    name: str
    bank: str
    currency: str
    is_active: bool
    created_at: dt.datetime


class AccountBalanceRead(BaseModel):
    account_id: int
    currency: str | None
    from_date: dt.date
    to_date: dt.date
    opening_balance: Decimal | None
    calculated_closing_balance: Decimal
    available_balance: Decimal
    statement_closing_balance: Decimal | None
    diff: Decimal | None
    pending_total: Decimal
    warning: str | None = None
