from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.statement_import import StatementImport
from app.schemas.imports import PDFImportResponse
from app.services.pdf_import_service import import_pdf_statement

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/pdf-statement", response_model=PDFImportResponse)
async def import_pdf_statement_endpoint(
    file: UploadFile = File(...),
    account_id: int | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
) -> PDFImportResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    file_bytes = await file.read()
    try:
        result = await import_pdf_statement(session, file_bytes, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.account_id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account is not resolved")

    statement_import = StatementImport(
        source="pdf",
        filename=filename or None,
        account_id=result.account_id,
        currency=result.currency,
        imported_period_from=result.period_from,
        imported_period_to=result.period_to,
        rows_total=result.rows_total,
        inserted=result.inserted,
        skipped=result.skipped,
    )
    session.add(statement_import)
    await session.commit()

    return PDFImportResponse(
        rows_total=result.rows_total,
        inserted=result.inserted,
        skipped=result.skipped,
        errors=result.errors,
    )
