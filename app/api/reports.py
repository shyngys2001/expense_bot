from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.category import Category
from app.models.enums import TransactionKind, TransactionStatus
from app.models.transaction import Transaction
from app.schemas.report import CategoryBreakdownItem, MonthlyReportResponse
from app.services.month import resolve_month_window
from app.services.reporting import KindAmount, summarize_kind_amounts

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly", response_model=MonthlyReportResponse)
async def monthly_report(
    month: str | None = Query(default=None, description="Месяц в формате YYYY-MM"),
    account_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReportResponse:
    try:
        month_start, month_end, _ = resolve_month_window(month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    base_filters = [Transaction.tx_date >= month_start, Transaction.tx_date < month_end]
    if account_id is not None:
        base_filters.append(Transaction.account_id == account_id)

    posted_filters = [*base_filters, Transaction.status == TransactionStatus.POSTED]

    amount_rows = await session.execute(
        select(Transaction.kind, Transaction.signed_amount).where(*posted_filters)
    )
    total_income, total_expense, total_transfers = summarize_kind_amounts(
        [KindAmount(kind=kind, signed_amount=signed_amount) for kind, signed_amount in amount_rows.all()]
    )

    category_rows = await session.execute(
        select(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .where(
            *posted_filters,
            Transaction.kind == TransactionKind.EXPENSE,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
    )

    breakdown = [
        CategoryBreakdownItem(category=name, total=total)
        for name, total in category_rows.all()
    ]

    total_pending = await session.scalar(
        select(func.coalesce(func.sum(func.abs(Transaction.signed_amount)), 0)).where(
            *base_filters,
            Transaction.status == TransactionStatus.PENDING,
        )
    )

    return MonthlyReportResponse(
        total_income=total_income,
        total_expense=total_expense,
        total_transfers=total_transfers,
        total_pending=total_pending or 0,
        balance=total_income - total_expense,
        breakdown_by_category=breakdown,
    )
