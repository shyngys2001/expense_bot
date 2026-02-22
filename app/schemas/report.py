from decimal import Decimal

from pydantic import BaseModel


class CategoryBreakdownItem(BaseModel):
    category: str
    total: Decimal


class MonthlyReportResponse(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    total_transfers: Decimal
    balance: Decimal
    breakdown_by_category: list[CategoryBreakdownItem]
