from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.account import Account
from app.models.statement_import import StatementImport
from app.models.transaction import Transaction
from app.schemas.imports import PDFImportResponse
from app.services.pdf_import_service import import_pdf_statement

router = APIRouter(prefix="/api/import", tags=["import"])
rollback_router = APIRouter(prefix="/api/imports", tags=["import"])


@router.post("/pdf-statement", response_model=PDFImportResponse)
async def import_pdf_statement_endpoint(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
) -> PDFImportResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только PDF-файлы",
        )
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    file_bytes = await file.read()
    statement_import = StatementImport(
        source="pdf",
        filename=filename or None,
        account_id=account_id,
    )
    session.add(statement_import)
    await session.flush()

    try:
        result = await import_pdf_statement(
            session=session,
            file_bytes=file_bytes,
            account_id=account_id,
            import_id=statement_import.id,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.account_id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось определить счет")

    statement_import.currency = result.currency
    statement_import.period_from = result.period_from
    statement_import.period_to = result.period_to
    statement_import.opening_balance = result.opening_balance
    statement_import.closing_balance = result.closing_balance
    statement_import.pending_balance = result.pending_balance
    statement_import.rows_total = result.rows_total
    statement_import.inserted = result.inserted
    statement_import.skipped = result.skipped
    await session.commit()

    return PDFImportResponse(
        import_id=statement_import.id,
        rows_total=result.rows_total,
        inserted=result.inserted,
        skipped=result.skipped,
        errors=result.errors,
    )


@rollback_router.post("/{import_id}/rollback")
async def rollback_import(
    import_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    statement_import = await session.get(StatementImport, import_id)
    if statement_import is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Импорт не найден")

    result = await session.execute(delete(Transaction).where(Transaction.import_id == import_id))
    deleted = result.rowcount or 0
    await session.commit()
    return {"import_id": import_id, "deleted": deleted}
