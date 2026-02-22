from pydantic import BaseModel

from app.models.enums import TransactionType


class CategoryRead(BaseModel):
    id: int
    name: str
    type: TransactionType
