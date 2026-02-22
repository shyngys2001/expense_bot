import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.account import Account
from app.schemas.account import AccountBalanceRead, AccountRead
from app.services.balance_service import get_account_balance

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list[AccountRead]:
    query = select(Account).order_by(Account.is_active.desc(), Account.name.asc())
    if active_only:
        query = query.where(Account.is_active.is_(True))

    rows = await session.scalars(query)
    return [
        AccountRead(
            id=item.id,
            name=item.name,
            bank=item.bank,
            currency=item.currency,
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in rows.all()
    ]


@router.get("/accounts/{account_id}/balance", response_model=AccountBalanceRead)
async def get_account_balance_endpoint(
    account_id: int,
    from_date: dt.date = Query(alias="from"),
    to_date: dt.date = Query(alias="to"),
    include_pending: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> AccountBalanceRead:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    result = await get_account_balance(
        session=session,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        include_pending=include_pending,
    )
    return AccountBalanceRead(
        account_id=result.account_id,
        currency=result.currency or account.currency,
        from_date=result.from_date,
        to_date=result.to_date,
        opening_balance=result.opening_balance,
        calculated_closing_balance=result.calculated_closing_balance,
        available_balance=result.available_balance,
        statement_closing_balance=result.statement_closing_balance,
        diff=result.diff,
        pending_total=result.pending_total,
        warning=result.warning,
    )
