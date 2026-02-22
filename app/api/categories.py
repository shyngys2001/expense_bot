from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.category import Category
from app.models.enums import TransactionType
from app.schemas.category import CategoryRead

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    type: TransactionType | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryRead]:
    query = select(Category).order_by(Category.type.asc(), Category.name.asc())
    if type is not None:
        query = query.where(Category.type == type)

    rows = await session.scalars(query)
    categories = rows.all()
    return [CategoryRead(id=item.id, name=item.name, type=item.type) for item in categories]
