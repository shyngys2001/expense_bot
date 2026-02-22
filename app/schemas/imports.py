from pydantic import BaseModel


class PDFImportResponse(BaseModel):
    import_id: int
    rows_total: int
    inserted: int
    skipped: int
    errors: list[str]
