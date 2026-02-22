import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.category import Category
from app.models.enums import TransactionKind, TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import (
    QuickAddRequest,
    TransactionCreate,
    TransactionDebugRead,
    TransactionRead,
    TransactionUpdate,
)
from app.services.accounts import resolve_account_id
from app.services.categorization_service import apply_category
from app.services.month import resolve_month_window
from app.services.quick_add import parse_quick_add_text
from app.services.transactions import serialize_transaction

router = APIRouter(prefix="/api", tags=["transactions"])


@router.post("/quick-add", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def quick_add_transaction(
    payload: QuickAddRequest,
    session: AsyncSession = Depends(get_session),
) -> TransactionRead:
    try:
        parsed = parse_quick_add_text(payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        account_id = await resolve_account_id(session, payload.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден") from exc

    transaction = Transaction(
        description=parsed.description,
        amount=parsed.amount,
        signed_amount=parsed.amount if parsed.tx_type == TransactionType.INCOME else -parsed.amount,
        currency=parsed.currency,
        type=parsed.tx_type,
        kind=TransactionKind(parsed.tx_type.value),
        status=TransactionStatus.POSTED,
        account_id=account_id,
        category_id=0,
        category_locked=False,
        source=TransactionSource.MANUAL,
        tx_date=dt.date.today(),
    )
    try:
        await apply_category(session, transaction)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка автокатегоризации") from exc

    session.add(transaction)
    await session.commit()

    saved_transaction = await session.scalar(
        select(Transaction)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.account),
            selectinload(Transaction.matched_account),
        )
        .where(Transaction.id == transaction.id)
    )
    if saved_transaction is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Операция не найдена")

    return serialize_transaction(saved_transaction)


@router.get("/transactions", response_model=list[TransactionRead])
async def list_transactions(
    month: str | None = Query(default=None, description="Месяц в формате YYYY-MM"),
    account_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> list[TransactionRead]:
    try:
        month_start, month_end, _ = resolve_month_window(month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    filters = [Transaction.tx_date >= month_start, Transaction.tx_date < month_end]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)

    result = await session.scalars(
        select(Transaction)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.account),
            selectinload(Transaction.matched_account),
        )
        .where(*filters)
        .order_by(Transaction.tx_date.desc(), Transaction.id.desc())
    )
    transactions = result.all()
    return [serialize_transaction(item) for item in transactions]


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    session: AsyncSession = Depends(get_session),
) -> TransactionRead:
    transaction = Transaction(
        description=payload.description.strip(),
        amount=payload.amount,
        signed_amount=payload.amount if payload.type == TransactionType.INCOME else -payload.amount,
        currency=payload.currency,
        type=payload.type,
        kind=TransactionKind(payload.type.value),
        status=TransactionStatus.POSTED,
        category_id=0,
        account_id=0,
        tx_date=payload.tx_date or dt.date.today(),
        source=TransactionSource.MANUAL,
        category_locked=False,
    )
    try:
        transaction.account_id = await resolve_account_id(session, payload.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден") from exc

    if payload.category_id is not None:
        category = await session.get(Category, payload.category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")

        if category.type != payload.type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Тип категории не совпадает с типом операции",
            )
        transaction.category_id = payload.category_id
        transaction.category_locked = True
    else:
        try:
            await apply_category(session, transaction)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка автокатегоризации",
            ) from exc

    session.add(transaction)
    await session.commit()

    saved_transaction = await session.scalar(
        select(Transaction)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.account),
            selectinload(Transaction.matched_account),
        )
        .where(Transaction.id == transaction.id)
    )
    if saved_transaction is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Операция не найдена")

    return serialize_transaction(saved_transaction)


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Операция не найдена")

    await session.delete(transaction)
    await session.commit()
    return {"status": "ok"}


@router.get("/transactions/{transaction_id}/debug", response_model=TransactionDebugRead)
async def transaction_debug(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
) -> TransactionDebugRead:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Операция не найдена")

    return TransactionDebugRead(
        id=transaction.id,
        source=transaction.source,
        import_id=transaction.import_id,
        account_id=transaction.account_id,
        raw=transaction.raw,
        external_hash=transaction.external_hash,
        created_at=transaction.created_at,
    )


@router.patch("/transactions/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: AsyncSession = Depends(get_session),
) -> TransactionRead:
    transaction = await session.scalar(
        select(Transaction)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.account),
            selectinload(Transaction.matched_account),
        )
        .where(Transaction.id == transaction_id)
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Операция не найдена")

    if payload.category_id is None and payload.category_locked is None and payload.kind is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нужно передать хотя бы одно поле: category_id, category_locked или kind",
        )

    category_changed = False
    selected_category = transaction.category
    if payload.category_id is not None:
        category = await session.get(Category, payload.category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
        if category.type != transaction.type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Тип категории не совпадает с типом операции",
            )

        category_changed = payload.category_id != transaction.category_id
        transaction.category_id = payload.category_id
        transaction.category = category
        selected_category = category

    if payload.category_locked is not None:
        transaction.category_locked = payload.category_locked
    elif category_changed:
        transaction.category_locked = True

    if payload.kind is not None:
        if payload.kind == TransactionKind.TRANSFER:
            transaction.kind = TransactionKind.TRANSFER
            transaction.transfer_pair_id = None
            transaction.matched_account_id = None
            transaction.matched_account = None
            transaction.match_confidence = 100
        else:
            transaction.kind = payload.kind
            transaction.type = TransactionType(payload.kind.value)
            transaction.transfer_pair_id = None
            transaction.matched_account_id = None
            transaction.matched_account = None
            transaction.match_confidence = 100
            transaction.signed_amount = (
                transaction.amount
                if payload.kind == TransactionKind.INCOME
                else -transaction.amount
            )

    await session.commit()

    if selected_category is None:
        selected_category = await session.get(Category, transaction.category_id)
    transaction.category = selected_category

    return serialize_transaction(transaction)
