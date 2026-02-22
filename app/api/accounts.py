from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.account import Account
from app.schemas.account import AccountRead

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
