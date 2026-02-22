from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.statement_import import StatementImport
from app.models.transaction import Transaction
from app.models.enums import TransactionStatus


@dataclass(slots=True)
class BalanceResult:
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


async def _find_statement_for_period(
    session: AsyncSession,
    account_id: int,
    from_date: dt.date,
    to_date: dt.date,
) -> StatementImport | None:
    covering = await session.scalar(
        select(StatementImport)
        .where(
            StatementImport.account_id == account_id,
            StatementImport.period_from.is_not(None),
            StatementImport.period_to.is_not(None),
            StatementImport.period_from <= from_date,
            StatementImport.period_to >= to_date,
        )
        .order_by(StatementImport.period_to.desc(), StatementImport.created_at.desc())
        .limit(1)
    )
    if covering is not None:
        return covering

    nearest = await session.scalar(
        select(StatementImport)
        .where(
            StatementImport.account_id == account_id,
            StatementImport.period_from.is_not(None),
            StatementImport.period_to.is_not(None),
            StatementImport.period_to >= from_date,
            StatementImport.period_from <= to_date,
        )
        .order_by(StatementImport.period_to.desc(), StatementImport.created_at.desc())
        .limit(1)
    )
    if nearest is not None:
        return nearest

    return await session.scalar(
        select(StatementImport)
        .where(StatementImport.account_id == account_id)
        .order_by(StatementImport.created_at.desc())
        .limit(1)
    )


async def get_account_balance(
    session: AsyncSession,
    account_id: int,
    from_date: dt.date,
    to_date: dt.date,
    include_pending: bool = False,
) -> BalanceResult:
    statement = await _find_statement_for_period(session, account_id, from_date, to_date)
    opening_balance = statement.opening_balance if statement is not None else None
    statement_closing = statement.closing_balance if statement is not None else None
    currency = statement.currency if statement is not None else None

    posted_sum = await session.scalar(
        select(func.coalesce(func.sum(Transaction.signed_amount), Decimal("0")))
        .where(
            Transaction.account_id == account_id,
            Transaction.tx_date >= from_date,
            Transaction.tx_date <= to_date,
            Transaction.status == TransactionStatus.POSTED,
        )
    )
    pending_sum = await session.scalar(
        select(func.coalesce(func.sum(func.abs(Transaction.signed_amount)), Decimal("0")))
        .where(
            Transaction.account_id == account_id,
            Transaction.tx_date >= from_date,
            Transaction.tx_date <= to_date,
            Transaction.status == TransactionStatus.PENDING,
        )
    )
    if pending_sum is None:
        pending_sum = Decimal("0")
    if posted_sum is None:
        posted_sum = Decimal("0")
    if statement is not None and statement.pending_balance is not None and pending_sum == Decimal("0"):
        pending_sum = abs(statement.pending_balance)

    opening_value = opening_balance if opening_balance is not None else Decimal("0")
    calculated_closing = opening_value + posted_sum
    available = calculated_closing - pending_sum if include_pending else calculated_closing
    diff = None if statement_closing is None else calculated_closing - statement_closing

    warning = None
    if opening_balance is None:
        warning = "Нет начального остатка в выписке, расчёт выполнен от 0."
    if (
        statement is not None
        and statement.pending_balance is not None
        and pending_sum != abs(statement.pending_balance)
    ):
        pending_warning = "Сумма pending по операциям отличается от pending в шапке выписки."
        warning = f"{warning} {pending_warning}".strip() if warning else pending_warning

    return BalanceResult(
        account_id=account_id,
        currency=currency,
        from_date=from_date,
        to_date=to_date,
        opening_balance=opening_balance,
        calculated_closing_balance=calculated_closing,
        available_balance=available,
        statement_closing_balance=statement_closing,
        diff=diff,
        pending_total=pending_sum,
        warning=warning,
    )
