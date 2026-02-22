import datetime as dt

from pydantic import BaseModel


class AccountRead(BaseModel):
    id: int
    name: str
    bank: str
    currency: str
    is_active: bool
    created_at: dt.datetime
