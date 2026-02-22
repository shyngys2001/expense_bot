from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import TransactionKind


@dataclass(slots=True)
class KindAmount:
    kind: TransactionKind
    signed_amount: Decimal


def summarize_kind_amounts(rows: list[KindAmount]) -> tuple[Decimal, Decimal, Decimal]:
    total_income = Decimal("0")
    total_expense = Decimal("0")
    total_transfers = Decimal("0")

    for row in rows:
        if row.kind == TransactionKind.INCOME:
            total_income += abs(row.signed_amount)
        elif row.kind == TransactionKind.EXPENSE:
            total_expense += abs(row.signed_amount)
        elif row.kind == TransactionKind.TRANSFER and row.signed_amount < 0:
            total_transfers += abs(row.signed_amount)

    return total_income, total_expense, total_transfers
