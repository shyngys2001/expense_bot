from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import TransactionKind
from app.models.transaction import Transaction

TRANSFER_KEYWORDS = (
    "перевод",
    "пополнение",
    "card to card",
    "kaspi",
    "freedom",
    "transfer",
)
BANK_HINTS = ("kaspi", "freedom", "halyk", "jusan", "bcc", "card")


@dataclass(slots=True)
class MatchableTransaction:
    id: int
    account_id: int
    tx_date: dt.date
    currency: str
    signed_amount: Decimal
    description: str


@dataclass(slots=True)
class CandidatePair:
    expense_id: int
    income_id: int
    confidence: int
    date_delta_days: int
    amount_delta: Decimal


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().replace("\xa0", " ").split())


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(needle in normalized for needle in needles)


def compute_confidence(expense: MatchableTransaction, income: MatchableTransaction) -> int:
    score = 70
    if _contains_any(expense.description, TRANSFER_KEYWORDS) or _contains_any(income.description, TRANSFER_KEYWORDS):
        score += 10
    if _contains_any(expense.description, BANK_HINTS) and _contains_any(income.description, BANK_HINTS):
        score += 10
    if expense.tx_date == income.tx_date:
        score += 10
    return min(score, 100)


def build_candidate_pairs(
    transactions: list[MatchableTransaction],
    window_days: int = 1,
    tolerance: Decimal = Decimal("0"),
) -> tuple[list[CandidatePair], int]:
    expenses = [item for item in transactions if item.signed_amount < 0]
    incomes = [item for item in transactions if item.signed_amount > 0]

    reviewed_candidates = 0
    candidates: list[CandidatePair] = []

    for expense in expenses:
        expense_abs = abs(expense.signed_amount)
        for income in incomes:
            if expense.account_id == income.account_id:
                continue
            if expense.currency != income.currency:
                continue

            date_delta_days = abs((income.tx_date - expense.tx_date).days)
            if date_delta_days > window_days:
                continue

            amount_delta = abs(expense_abs - income.signed_amount)
            if amount_delta > tolerance:
                continue

            reviewed_candidates += 1
            candidates.append(
                CandidatePair(
                    expense_id=expense.id,
                    income_id=income.id,
                    confidence=compute_confidence(expense, income),
                    date_delta_days=date_delta_days,
                    amount_delta=amount_delta,
                )
            )

    return candidates, reviewed_candidates


def choose_pairs(candidates: list[CandidatePair], threshold: int = 80) -> list[CandidatePair]:
    sorted_candidates = sorted(
        (item for item in candidates if item.confidence >= threshold),
        key=lambda item: (
            -item.confidence,
            item.date_delta_days,
            item.amount_delta,
            item.expense_id,
            item.income_id,
        ),
    )

    used_transactions: set[int] = set()
    accepted: list[CandidatePair] = []
    for item in sorted_candidates:
        if item.expense_id in used_transactions or item.income_id in used_transactions:
            continue
        used_transactions.add(item.expense_id)
        used_transactions.add(item.income_id)
        accepted.append(item)

    return accepted


async def auto_pair_transfers(
    session: AsyncSession,
    from_date: dt.date,
    to_date: dt.date,
    account_ids: list[int] | None = None,
    window_days: int = 1,
    tolerance: Decimal = Decimal("0"),
    threshold: int = 80,
) -> tuple[int, int]:
    filters = [
        Transaction.tx_date >= from_date,
        Transaction.tx_date <= to_date,
        Transaction.transfer_pair_id.is_(None),
        Transaction.kind != TransactionKind.TRANSFER,
        or_(Transaction.signed_amount > 0, Transaction.signed_amount < 0),
    ]
    if account_ids:
        filters.append(Transaction.account_id.in_(account_ids))

    rows = await session.scalars(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.tx_date.asc(), Transaction.id.asc())
    )
    transactions = rows.all()
    tx_map = {item.id: item for item in transactions}

    candidates, reviewed_candidates = build_candidate_pairs(
        [
            MatchableTransaction(
                id=item.id,
                account_id=item.account_id,
                tx_date=item.tx_date,
                currency=item.currency,
                signed_amount=item.signed_amount,
                description=item.description,
            )
            for item in transactions
        ],
        window_days=window_days,
        tolerance=tolerance,
    )
    accepted_pairs = choose_pairs(candidates, threshold=threshold)

    for pair in accepted_pairs:
        pair_id = uuid4()
        expense = tx_map[pair.expense_id]
        income = tx_map[pair.income_id]

        expense.kind = TransactionKind.TRANSFER
        expense.transfer_pair_id = pair_id
        expense.matched_account_id = income.account_id
        expense.match_confidence = pair.confidence

        income.kind = TransactionKind.TRANSFER
        income.transfer_pair_id = pair_id
        income.matched_account_id = expense.account_id
        income.match_confidence = pair.confidence

    await session.commit()
    return len(accepted_pairs), reviewed_candidates


async def get_transfer_pairs(
    session: AsyncSession,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
) -> list[tuple[Transaction, Transaction]]:
    filters = [Transaction.kind == TransactionKind.TRANSFER, Transaction.transfer_pair_id.is_not(None)]
    if from_date is not None:
        filters.append(Transaction.tx_date >= from_date)
    if to_date is not None:
        filters.append(Transaction.tx_date <= to_date)

    rows = await session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.account), selectinload(Transaction.matched_account))
        .where(and_(*filters))
        .order_by(Transaction.transfer_pair_id.asc(), Transaction.id.asc())
    )
    grouped: dict[object, list[Transaction]] = {}
    for transaction in rows.all():
        if transaction.transfer_pair_id is None:
            continue
        grouped.setdefault(transaction.transfer_pair_id, []).append(transaction)

    result: list[tuple[Transaction, Transaction]] = []
    for pair in grouped.values():
        if len(pair) < 2:
            continue
        pair_sorted = sorted(pair[:2], key=lambda item: (item.signed_amount >= 0, item.id))
        result.append((pair_sorted[0], pair_sorted[1]))
    return result
