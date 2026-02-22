from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pdfplumber
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionKind, TransactionType
from app.models.transaction import Transaction
from app.services.accounts import resolve_account_id
from app.services.categorization_service import apply_category

TABLE_HEADER = "Дата Сумма Валюта Операция Детали"

ROW_START_PATTERN = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+([+-]?\d[\d\s]*,\d{2}|\+?\d[\d\s]*\.\d{2}|\-?\d[\d\s]*\.\d{2})\s*(₸|\$)?\s+(KZT|USD)\s+(.+)$"
)

# Fallback for rows where amount includes thousands separator commas (e.g. 203,210.00).
ROW_START_PATTERN_FALLBACK = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+([+-]?\d[\d\s,]*[\.,]\d{2})\s*(₸|\$)?\s+(KZT|USD)\s+(.+)$"
)

DATE_LINE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}\b")

KNOWN_OPERATIONS = (
    "Сумма в обработке",
    "Пополнение",
    "Перевод",
    "Покупка",
    "Другое",
)


@dataclass(slots=True)
class ParsedStatementRow:
    tx_date: dt.date
    signed_amount: Decimal
    amount: Decimal
    tx_type: TransactionType
    currency: str
    operation: str
    details: str
    description: str
    external_hash: str
    signed_amount_text: str
    page_no: int
    row_text: str


@dataclass(slots=True)
class PDFImportResult:
    rows_total: int
    inserted: int
    skipped: int
    errors: list[str]
    account_id: int | None = None
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    currency: str | None = None


def _normalize_spaces(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _parse_signed_amount(raw_amount: str) -> Decimal:
    normalized = raw_amount.replace("\xa0", "").replace(" ", "")

    if "," in normalized and "." in normalized:
        if normalized.rfind(".") > normalized.rfind(","):
            normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", ".")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount value: {raw_amount}") from exc


def _split_operation_and_details(payload: str) -> tuple[str, str]:
    normalized = payload.strip()
    for operation in KNOWN_OPERATIONS:
        match = re.search(rf"(?<!\\S){re.escape(operation)}(?!\\S)", normalized)
        if match:
            details = normalized[match.end() :].strip()
            return operation, details

    return "Другое", normalized


def make_external_hash(
    tx_date: dt.date,
    signed_amount: Decimal,
    currency: str,
    operation: str,
    details: str,
) -> str:
    payload = f"{tx_date.isoformat()}|{signed_amount}|{currency}|{operation}|{details}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_statement_line(row_text: str, page_no: int) -> ParsedStatementRow:
    normalized_line = _normalize_spaces(row_text)
    match = ROW_START_PATTERN.match(normalized_line)
    if match is None:
        match = ROW_START_PATTERN_FALLBACK.match(normalized_line)

    if match is None:
        raise ValueError(f"Could not parse row on page {page_no}: {row_text}")

    date_raw, signed_amount_text, _, currency_raw, payload = match.groups()

    tx_date = dt.datetime.strptime(date_raw, "%d.%m.%Y").date()
    signed_amount = _parse_signed_amount(signed_amount_text)
    if signed_amount == 0:
        raise ValueError(f"Zero amount is not supported on page {page_no}: {row_text}")

    tx_type = TransactionType.EXPENSE if signed_amount < 0 else TransactionType.INCOME
    amount = abs(signed_amount)

    currency = currency_raw.upper()
    if currency not in {"KZT", "USD"}:
        raise ValueError(f"Unsupported currency '{currency}' on page {page_no}")

    operation, details = _split_operation_and_details(payload)
    description = f"{operation} {details}".strip() if details else operation

    external_hash = make_external_hash(tx_date, signed_amount, currency, operation, details)

    return ParsedStatementRow(
        tx_date=tx_date,
        signed_amount=signed_amount,
        amount=amount,
        tx_type=tx_type,
        currency=currency,
        operation=operation,
        details=details,
        description=description,
        external_hash=external_hash,
        signed_amount_text=signed_amount_text,
        page_no=page_no,
        row_text=normalized_line,
    )


def _extract_page_texts(file_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        plumber_texts = [page.extract_text() or "" for page in pdf.pages]

    reader = PdfReader(io.BytesIO(file_bytes))
    pypdf_texts = [page.extract_text() or "" for page in reader.pages]

    page_texts: list[str] = []
    for index, plumber_text in enumerate(plumber_texts):
        if plumber_text.strip():
            page_texts.append(plumber_text)
            continue

        fallback_text = pypdf_texts[index] if index < len(pypdf_texts) else ""
        page_texts.append(fallback_text)

    return page_texts


def _collect_candidate_rows(page_texts: list[str]) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    current_row: str | None = None
    current_page_no = 0

    for page_no, page_text in enumerate(page_texts, start=1):
        lines = [_normalize_spaces(line) for line in page_text.splitlines()]
        lines = [line for line in lines if line]

        header_index = next((idx for idx, line in enumerate(lines) if line == TABLE_HEADER), -1)
        rows_area = lines[header_index + 1 :] if header_index >= 0 else lines

        for line in rows_area:
            if DATE_LINE_PATTERN.match(line):
                if current_row is not None:
                    collected.append((current_page_no, current_row))
                current_row = line
                current_page_no = page_no
            elif current_row is not None:
                current_row = f"{current_row} {line}".strip()

    if current_row is not None:
        collected.append((current_page_no, current_row))

    return collected


def parse_statement_rows_from_page_texts(page_texts: list[str]) -> tuple[list[ParsedStatementRow], list[str], int]:
    candidates = _collect_candidate_rows(page_texts)
    rows: list[ParsedStatementRow] = []
    errors: list[str] = []

    for page_no, row_text in candidates:
        try:
            rows.append(parse_statement_line(row_text, page_no))
        except ValueError as exc:
            errors.append(str(exc))

    return rows, errors, len(candidates)


def deduplicate_rows(
    rows: list[ParsedStatementRow],
    existing_hashes: set[str],
) -> tuple[list[ParsedStatementRow], int]:
    unique_rows: list[ParsedStatementRow] = []
    skipped = 0
    in_file_hashes: set[str] = set()

    for row in rows:
        if row.external_hash in existing_hashes or row.external_hash in in_file_hashes:
            skipped += 1
            continue
        in_file_hashes.add(row.external_hash)
        unique_rows.append(row)

    return unique_rows, skipped


async def import_pdf_statement(
    session: AsyncSession,
    file_bytes: bytes,
    account_id: int | None = None,
) -> PDFImportResult:
    if not file_bytes:
        raise ValueError("File is empty")

    try:
        page_texts = _extract_page_texts(file_bytes)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Failed to read PDF statement") from exc
    try:
        resolved_account_id = await resolve_account_id(session, account_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    parsed_rows, errors, rows_total = parse_statement_rows_from_page_texts(page_texts)

    if not parsed_rows:
        return PDFImportResult(
            rows_total=rows_total,
            inserted=0,
            skipped=0,
            errors=errors,
            account_id=resolved_account_id,
        )

    hashes = [row.external_hash for row in parsed_rows]
    existing_result = await session.scalars(
        select(Transaction.external_hash).where(Transaction.external_hash.in_(hashes))
    )
    existing_hashes = {value for value in existing_result.all() if value is not None}

    unique_rows, skipped = deduplicate_rows(parsed_rows, existing_hashes)

    inserted = 0
    for row in unique_rows:
        try:
            transaction = Transaction(
                description=row.description,
                amount=row.amount,
                signed_amount=row.signed_amount,
                currency=row.currency,
                type=row.tx_type,
                kind=TransactionKind(row.tx_type.value),
                account_id=resolved_account_id,
                category_id=0,
                tx_date=row.tx_date,
                source="import_pdf",
                external_hash=row.external_hash,
                category_locked=False,
                raw={
                    "operation": row.operation,
                    "details": row.details,
                    "signed_amount_text": row.signed_amount_text,
                    "page_no": row.page_no,
                    "row_text": row.row_text,
                },
            )
            await apply_category(session, transaction)
            session.add(transaction)
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to insert row (page {row.page_no}): {exc}")

    await session.commit()

    currencies = {row.currency for row in parsed_rows}
    dates = [row.tx_date for row in parsed_rows]

    return PDFImportResult(
        rows_total=rows_total,
        inserted=inserted,
        skipped=skipped,
        errors=errors,
        account_id=resolved_account_id,
        period_from=min(dates) if dates else None,
        period_to=max(dates) if dates else None,
        currency=currencies.pop() if len(currencies) == 1 else None,
    )
