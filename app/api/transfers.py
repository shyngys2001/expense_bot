import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.transfer import (
    AutoPairRequest,
    AutoPairResponse,
    TransferPairRead,
    TransferPairTransaction,
)
from app.services.transfer_matcher import auto_pair_transfers, get_transfer_pairs

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


@router.post("/auto-pair", response_model=AutoPairResponse)
async def auto_pair_endpoint(
    payload: AutoPairRequest,
    session: AsyncSession = Depends(get_session),
) -> AutoPairResponse:
    paired, reviewed_candidates = await auto_pair_transfers(
        session=session,
        from_date=payload.from_date,
        to_date=payload.to_date,
        account_ids=payload.account_ids,
        window_days=payload.window_days,
        tolerance=payload.tolerance,
        threshold=payload.threshold,
    )
    return AutoPairResponse(paired=paired, reviewed_candidates=reviewed_candidates)


@router.get("/pairs", response_model=list[TransferPairRead])
async def list_transfer_pairs_endpoint(
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
) -> list[TransferPairRead]:
    pairs = await get_transfer_pairs(session=session, from_date=from_date, to_date=to_date)
    response: list[TransferPairRead] = []
    for left, right in pairs:
        if left.transfer_pair_id is None:
            continue
        response.append(
            TransferPairRead(
                transfer_pair_id=left.transfer_pair_id,
                confidence=max(left.match_confidence or 0, right.match_confidence or 0),
                left=TransferPairTransaction(
                    transaction_id=left.id,
                    account_id=left.account_id,
                    account_name=left.account.name if left.account else "Неизвестно",
                    tx_date=left.tx_date,
                    signed_amount=left.signed_amount,
                    currency=left.currency,
                    description=left.description,
                ),
                right=TransferPairTransaction(
                    transaction_id=right.id,
                    account_id=right.account_id,
                    account_name=right.account.name if right.account else "Неизвестно",
                    tx_date=right.tx_date,
                    signed_amount=right.signed_amount,
                    currency=right.currency,
                    description=right.description,
                ),
            )
        )
    return response
