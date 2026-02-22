import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.enums import TransactionKind, TransactionType
from app.models.transaction import Transaction
from app.schemas.rule import RuleApplyResponse, RuleCreate, RuleRead, RuleUpdate
from app.services.categorization_service import find_category_for
from app.services.month import resolve_month_window

router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/rules", response_model=list[RuleRead])
async def list_rules(
    type: TransactionType | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[RuleRead]:
    query = (
        select(CategoryRule, Category)
        .join(Category, CategoryRule.category_id == Category.id)
        .order_by(CategoryRule.priority.desc(), CategoryRule.created_at.desc())
    )

    if type is not None:
        query = query.where(Category.type == type)

    rows = await session.execute(query)
    response: list[RuleRead] = []
    for rule, category in rows.all():
        response.append(
            RuleRead(
                id=rule.id,
                pattern=rule.pattern,
                match_type=rule.match_type,
                category_id=rule.category_id,
                category_name=category.name,
                category_type=category.type.value,
                priority=rule.priority,
                is_active=rule.is_active,
                created_at=rule.created_at,
            )
        )
    return response


@router.post("/rules", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(payload: RuleCreate, session: AsyncSession = Depends(get_session)) -> RuleRead:
    category = await session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    rule = CategoryRule(
        pattern=payload.pattern,
        match_type=payload.match_type,
        category_id=payload.category_id,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    return RuleRead(
        id=rule.id,
        pattern=rule.pattern,
        match_type=rule.match_type,
        category_id=rule.category_id,
        category_name=category.name,
        category_type=category.type.value,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.patch("/rules/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    session: AsyncSession = Depends(get_session),
) -> RuleRead:
    rule = await session.get(CategoryRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    if payload.pattern is not None:
        rule.pattern = payload.pattern
    if payload.match_type is not None:
        rule.match_type = payload.match_type
    if payload.priority is not None:
        rule.priority = payload.priority
    if payload.is_active is not None:
        rule.is_active = payload.is_active

    if payload.category_id is not None:
        category = await session.get(Category, payload.category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        rule.category_id = payload.category_id

    await session.commit()

    row = await session.execute(
        select(CategoryRule, Category)
        .join(Category, CategoryRule.category_id == Category.id)
        .where(CategoryRule.id == rule.id)
    )
    data = row.first()
    if data is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Rule not found")

    updated_rule, category = data
    return RuleRead(
        id=updated_rule.id,
        pattern=updated_rule.pattern,
        match_type=updated_rule.match_type,
        category_id=updated_rule.category_id,
        category_name=category.name,
        category_type=category.type.value,
        priority=updated_rule.priority,
        is_active=updated_rule.is_active,
        created_at=updated_rule.created_at,
    )


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    rule = await session.get(CategoryRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await session.delete(rule)
    await session.commit()
    return {"status": "ok"}


@router.post("/rules/apply", response_model=RuleApplyResponse)
async def apply_rules_to_transactions(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
) -> RuleApplyResponse:
    if month and (from_date or to_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use either month or from/to range",
        )

    if month:
        range_start, range_end, _ = resolve_month_window(month)
    else:
        range_start = from_date
        range_end = to_date + dt.timedelta(days=1) if to_date else None

    filters = []
    if range_start is not None:
        filters.append(Transaction.tx_date >= range_start)
    if range_end is not None:
        filters.append(Transaction.tx_date < range_end)

    rows = await session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.category))
        .where(*filters)
        .order_by(Transaction.id.asc())
    )
    transactions = rows.all()

    processed = 0
    updated = 0
    skipped_locked = 0

    for transaction in transactions:
        processed += 1
        if transaction.category_locked or transaction.kind == TransactionKind.TRANSFER:
            skipped_locked += 1
            continue

        new_category_id = await find_category_for(session, transaction.description, transaction.type)
        if new_category_id != transaction.category_id:
            transaction.category_id = new_category_id
            updated += 1

    await session.commit()

    return RuleApplyResponse(processed=processed, updated=updated, skipped_locked=skipped_locked)
