from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.category import Category
from app.models.enums import TransactionKind
from app.models.transaction import Transaction
from app.schemas.report import CategoryBreakdownItem, MonthlyReportResponse
from app.services.month import resolve_month_window
from app.services.reporting import KindAmount, summarize_kind_amounts

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly", response_model=MonthlyReportResponse)
async def monthly_report(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    account_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReportResponse:
    try:
        month_start, month_end, _ = resolve_month_window(month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filters = [Transaction.tx_date >= month_start, Transaction.tx_date < month_end]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)

    amount_rows = await session.execute(
        select(Transaction.kind, Transaction.signed_amount).where(*filters)
    )
    total_income, total_expense, total_transfers = summarize_kind_amounts(
        [KindAmount(kind=kind, signed_amount=signed_amount) for kind, signed_amount in amount_rows.all()]
    )

    category_rows = await session.execute(
        select(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .where(
            *filters,
            Transaction.kind == TransactionKind.EXPENSE,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
    )

    breakdown = [
        CategoryBreakdownItem(category=name, total=total)
        for name, total in category_rows.all()
    ]

    return MonthlyReportResponse(
        total_income=total_income,
        total_expense=total_expense,
        total_transfers=total_transfers,
        balance=total_income - total_expense,
        breakdown_by_category=breakdown,
    )
