from pydantic import BaseModel


class PDFImportResponse(BaseModel):
    rows_total: int
    inserted: int
    skipped: int
    errors: list[str]
