from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account

DEFAULT_ACCOUNT_NAME = "Main Account"


async def get_default_account(session: AsyncSession) -> Account:
    default_account = await session.scalar(
        select(Account).where(Account.name == DEFAULT_ACCOUNT_NAME).limit(1)
    )
    if default_account is not None:
        return default_account

    any_account = await session.scalar(select(Account).order_by(Account.id.asc()).limit(1))
    if any_account is not None:
        return any_account

    created = Account(name=DEFAULT_ACCOUNT_NAME, bank="Unknown", currency="KZT", is_active=True)
    session.add(created)
    await session.flush()
    return created


async def resolve_account_id(session: AsyncSession, account_id: int | None) -> int:
    if account_id is None:
        return (await get_default_account(session)).id

    account = await session.get(Account, account_id)
    if account is None:
        raise ValueError("Account not found")
    return account.id
