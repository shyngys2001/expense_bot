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

from app.models.account import Account
from app.models.enums import TransactionKind, TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.services.categorization_service import apply_category

TABLE_HEADER = "Дата Сумма Валюта Операция Детали"
TABLE_HEADER_KASPI = "Дата Описание Сумма"

ROW_START_PATTERN = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+([+-]?\d[\d\s]*,\d{2}|\+?\d[\d\s]*\.\d{2}|\-?\d[\d\s]*\.\d{2})\s*(₸|\$)?\s+(KZT|USD)\s+(.+)$"
)

# Fallback for rows where amount includes thousands separator commas (e.g. 203,210.00).
ROW_START_PATTERN_FALLBACK = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+([+-]?\d[\d\s,]*[\.,]\d{2})\s*(₸|\$)?\s+(KZT|USD)\s+(.+)$"
)

DATE_LINE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}\b")
DATE_LINE_SHORT_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{2,4}\b")
DATE_START_PATTERN = re.compile(r"^(\d{2}\.\d{2}\.(\d{2}|\d{4}))\b")

KNOWN_OPERATIONS = (
    "Сумма в обработке",
    "Пополнение",
    "Перевод",
    "Покупка",
    "Другое",
)

TRANSFER_BALANCE_DATE_PATTERN = re.compile(r"(\d{2}\.\d{2}\.\d{2,4})")
AMOUNT_WITH_CURRENCY_PATTERN = re.compile(
    r"([+-]?\d[\d\s,]*[.,]\d{2})\s*(₸|KZT|\$|USD)",
    flags=re.IGNORECASE,
)
KASPI_AVAILABLE_DATE_ONLY_PATTERN = re.compile(
    r"Доступно на\s+(\d{2}\.\d{2}\.\d{2,4})",
    flags=re.IGNORECASE,
)
KASPI_AVAILABLE_LINE_PATTERN = re.compile(
    r"Доступно на\s+(\d{2}\.\d{2}\.\d{2,4}).*?([+-]?\d[\d\s,]*[.,]\d{2})",
    flags=re.IGNORECASE,
)
KASPI_AVAILABLE_LINE_PATTERN_ALT = re.compile(
    r"([+-]?\d[\d\s,]*[.,]\d{2}).*?Доступно на\s+(\d{2}\.\d{2}\.\d{2,4})",
    flags=re.IGNORECASE,
)
FREEDOM_PENDING_HEADER_PATTERN = re.compile(
    r"Сумма в обработке\s*[:\-]?\s*([+-]?\d[\d\s,]*[.,]\d{2})",
    flags=re.IGNORECASE,
)
FREEDOM_CLOSING_CURRENCY_LINE_PATTERN = re.compile(
    r"(?:остаток|доступно|баланс)[^\n]*?([+-]?\d[\d\s,]*[.,]\d{2})\s*(₸|KZT|\$|USD)",
    flags=re.IGNORECASE,
)
FREEDOM_STATEMENT_DATE_PATTERN = re.compile(
    r"(?:по состоянию на|на дату|дата формирования)\s+(\d{2}\.\d{2}\.\d{2,4})",
    flags=re.IGNORECASE,
)
KASPI_ROW_PATTERN = re.compile(
    r"^(?P<date>\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s+(?P<sign>[+-])\s*(?P<amount>\d[\d\s]*[.,]\d{2})\s*"
    r"(?P<cur>₸|\$|KZT|USD)?\s*(?P<rest>.+)$",
    flags=re.IGNORECASE,
)
IGNORED_CONTINUATION_PREFIXES = (
    "сумма в обработке по",
    "итого",
    "остаток",
    "доступно на",
    "страница",
    "дата ",
    "описание ",
    "сумма ",
    "выписка",
    "kaspi gold",
    "kaspi.kz",
)
MAX_IMPORT_ERRORS = 20


@dataclass(slots=True)
class StatementMetadata:
    bank_type: str
    period_from: dt.date | None
    period_to: dt.date | None
    opening_balance: Decimal | None
    closing_balance_by_currency: dict[str, Decimal]
    pending_balance: Decimal | None


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
    status: TransactionStatus
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
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    pending_balance: Decimal | None = None


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
        raise ValueError(f"Некорректная сумма: {raw_amount}") from exc


def _parse_statement_date(raw_date: str) -> dt.date:
    raw_date = raw_date.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return dt.datetime.strptime(raw_date, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Некорректная дата: {raw_date}")


def _currency_from_marker(marker: str | None) -> str:
    if marker is None:
        return "KZT"
    upper_marker = marker.upper()
    if upper_marker in {"₸", "KZT"}:
        return "KZT"
    if upper_marker in {"$", "USD"}:
        return "USD"
    return upper_marker


def _truncate_errors(errors: list[str], limit: int = MAX_IMPORT_ERRORS) -> list[str]:
    if errors and re.match(r"^и ещё \d+ строк\(и\) с ошибками$", errors[-1]):
        return errors
    if len(errors) <= limit:
        return errors
    remain = len(errors) - limit
    return [*errors[:limit], f"и ещё {remain} строк(и) с ошибками"]


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
    account_id: int | None = None,
) -> str:
    payload = f"{account_id or 0}|{tx_date.isoformat()}|{signed_amount}|{currency}|{operation}|{details}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_statement_line(row_text: str, page_no: int) -> ParsedStatementRow:
    normalized_line = _normalize_spaces(row_text)
    match = ROW_START_PATTERN.match(normalized_line)
    if match is None:
        match = ROW_START_PATTERN_FALLBACK.match(normalized_line)

    if match is None:
        raise ValueError(f"Не удалось разобрать строку на стр. {page_no}: {row_text}")

    date_raw, signed_amount_text, _, currency_raw, payload = match.groups()

    tx_date = _parse_statement_date(date_raw)
    signed_amount = _parse_signed_amount(signed_amount_text)
    if signed_amount == 0:
        raise ValueError(f"Нулевая сумма не поддерживается (стр. {page_no}): {row_text}")

    tx_type = TransactionType.EXPENSE if signed_amount < 0 else TransactionType.INCOME
    amount = abs(signed_amount)

    currency = currency_raw.upper()
    if currency not in {"KZT", "USD"}:
        raise ValueError(f"Неподдерживаемая валюта '{currency}' на стр. {page_no}")

    operation, details = _split_operation_and_details(payload)
    description = f"{operation} {details}".strip() if details else operation
    status = (
        TransactionStatus.PENDING
        if "сумма в обработке" in description.lower()
        else TransactionStatus.POSTED
    )

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
        status=status,
        external_hash=external_hash,
        signed_amount_text=signed_amount_text,
        page_no=page_no,
        row_text=normalized_line,
    )


def parse_kaspi_statement_line(row_text: str, page_no: int) -> ParsedStatementRow:
    normalized_line = _normalize_spaces(row_text)
    match = KASPI_ROW_PATTERN.match(normalized_line)
    if match is None:
        raise ValueError(f"Не удалось разобрать строку Kaspi на стр. {page_no}: {row_text}")

    date_raw = match.group("date")
    sign = match.group("sign")
    amount_raw = match.group("amount")
    marker = match.group("cur")
    rest = match.group("rest").strip()

    tx_date = _parse_statement_date(date_raw)

    parsed_amount = _parse_signed_amount(amount_raw)
    amount = abs(parsed_amount)
    if amount == 0:
        raise ValueError(f"Нулевая сумма не поддерживается (стр. {page_no}): {row_text}")
    signed_amount = amount if sign == "+" else -amount

    tx_type = TransactionType.EXPENSE if signed_amount < 0 else TransactionType.INCOME
    currency = _currency_from_marker(marker)
    if marker is None:
        if "₸" in rest:
            currency = "KZT"
        elif "$" in rest:
            currency = "USD"
        else:
            currency = "KZT"

    parts = rest.split(maxsplit=1)
    operation = parts[0] if parts else "Другое"
    details = parts[1].strip() if len(parts) > 1 else ""
    description = f"{operation} {details}".strip()
    status = (
        TransactionStatus.PENDING
        if "в обработке" in description.lower()
        else TransactionStatus.POSTED
    )
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
        status=status,
        external_hash=external_hash,
        signed_amount_text=f"{sign}{amount_raw}",
        page_no=page_no,
        row_text=normalized_line,
    )


def detect_bank_type(page_texts: list[str]) -> str:
    full_text = _normalize_spaces("\n".join(page_texts)).lower()
    if "kaspi" in full_text:
        return "kaspi"
    if "freedom" in full_text or "super card" in full_text:
        return "freedom"
    if "доступно на" in full_text:
        return "kaspi"
    return "freedom"


def _extract_kaspi_metadata(page_texts: list[str]) -> StatementMetadata:
    full_text = "\n".join(page_texts)
    lines = [_normalize_spaces(line) for line in full_text.splitlines() if _normalize_spaces(line)]
    available_entries: list[tuple[dt.date, Decimal]] = []
    for index, line in enumerate(lines):
        match = KASPI_AVAILABLE_LINE_PATTERN.search(line)
        if match:
            date_raw, amount_raw = match.groups()
            available_entries.append((_parse_statement_date(date_raw), _parse_signed_amount(amount_raw)))
            continue

        alt_match = KASPI_AVAILABLE_LINE_PATTERN_ALT.search(line)
        if alt_match:
            amount_raw, date_raw = alt_match.groups()
            available_entries.append((_parse_statement_date(date_raw), _parse_signed_amount(amount_raw)))
            continue

        date_only_match = KASPI_AVAILABLE_DATE_ONLY_PATTERN.search(line)
        if date_only_match:
            date_raw = date_only_match.group(1)
            amount_match = AMOUNT_WITH_CURRENCY_PATTERN.search(line)
            if amount_match is None:
                for next_line in lines[index + 1 : index + 3]:
                    amount_match = AMOUNT_WITH_CURRENCY_PATTERN.search(next_line)
                    if amount_match is not None:
                        break
            if amount_match:
                available_entries.append((_parse_statement_date(date_raw), _parse_signed_amount(amount_match.group(1))))

    available_entries = sorted(available_entries, key=lambda item: item[0])
    opening_balance = available_entries[0][1] if available_entries else None
    closing_balance = available_entries[-1][1] if available_entries else None
    period_from = available_entries[0][0] if available_entries else None
    period_to = available_entries[-1][0] if available_entries else None

    return StatementMetadata(
        bank_type="kaspi",
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
        closing_balance_by_currency={"KZT": closing_balance} if closing_balance is not None else {},
        pending_balance=None,
    )


def _extract_freedom_metadata(page_texts: list[str]) -> StatementMetadata:
    full_text = "\n".join(page_texts)
    table_index = full_text.find(TABLE_HEADER)
    header_text = full_text if table_index < 0 else full_text[:table_index]
    lines = [_normalize_spaces(line) for line in header_text.splitlines() if _normalize_spaces(line)]

    balances_by_currency: dict[str, Decimal] = {}
    pending_balance: Decimal | None = None
    period_to: dt.date | None = None

    for line in lines:
        pending_match = FREEDOM_PENDING_HEADER_PATTERN.search(line)
        if pending_match and pending_balance is None:
            pending_balance = abs(_parse_signed_amount(pending_match.group(1)))

        if period_to is None:
            statement_date_match = FREEDOM_STATEMENT_DATE_PATTERN.search(line)
            if statement_date_match:
                period_to = _parse_statement_date(statement_date_match.group(1))

        for amount_raw, marker in FREEDOM_CLOSING_CURRENCY_LINE_PATTERN.findall(line):
            currency = _currency_from_marker(marker)
            balances_by_currency[currency] = _parse_signed_amount(amount_raw)

    # Fallback if balances are not prefixed with "остаток|баланс".
    if not balances_by_currency:
        header_sample = "\n".join(lines[:30])
        for amount_raw, marker in AMOUNT_WITH_CURRENCY_PATTERN.findall(header_sample):
            currency = _currency_from_marker(marker)
            balances_by_currency.setdefault(currency, _parse_signed_amount(amount_raw))

    return StatementMetadata(
        bank_type="freedom",
        period_from=None,
        period_to=period_to,
        opening_balance=None,
        closing_balance_by_currency=balances_by_currency,
        pending_balance=pending_balance,
    )


def extract_statement_metadata(page_texts: list[str]) -> StatementMetadata:
    bank_type = detect_bank_type(page_texts)
    if bank_type == "kaspi":
        return _extract_kaspi_metadata(page_texts)
    return _extract_freedom_metadata(page_texts)


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


def _collect_candidate_rows(page_texts: list[str], bank_type: str) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    current_row: str | None = None
    current_page_no = 0

    for page_no, page_text in enumerate(page_texts, start=1):
        lines = [_normalize_spaces(line) for line in page_text.splitlines()]
        lines = [line for line in lines if line]

        headers = [TABLE_HEADER]
        if bank_type == "kaspi":
            headers.append(TABLE_HEADER_KASPI)

        header_index = next((idx for idx, line in enumerate(lines) if line in headers), -1)
        rows_area = lines[header_index + 1 :] if header_index >= 0 else lines

        for line in rows_area:
            if DATE_START_PATTERN.match(line):
                if current_row is not None:
                    collected.append((current_page_no, current_row))
                current_row = line
                current_page_no = page_no
            elif current_row is not None:
                normalized_lower = line.lower()
                if line in headers:
                    continue
                if any(normalized_lower.startswith(prefix) for prefix in IGNORED_CONTINUATION_PREFIXES):
                    continue
                current_row = f"{current_row} {line}".strip()

    if current_row is not None:
        collected.append((current_page_no, current_row))

    return collected


def parse_statement_rows_from_page_texts(
    page_texts: list[str],
    bank_type: str,
) -> tuple[list[ParsedStatementRow], list[str], int]:
    candidates = _collect_candidate_rows(page_texts, bank_type=bank_type)
    rows: list[ParsedStatementRow] = []
    errors: list[str] = []

    for page_no, row_text in candidates:
        try:
            if bank_type == "kaspi":
                rows.append(parse_kaspi_statement_line(row_text, page_no))
            else:
                rows.append(parse_statement_line(row_text, page_no))
        except ValueError as exc:
            errors.append(str(exc))

    return rows, _truncate_errors(errors), len(candidates)


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
    account_id: int,
    import_id: int,
) -> PDFImportResult:
    if not file_bytes:
        raise ValueError("Файл пуст")

    try:
        page_texts = _extract_page_texts(file_bytes)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Не удалось прочитать PDF-выписку") from exc
    account_currency = await session.scalar(
        select(Account.currency).where(Account.id == account_id).limit(1)
    )
    if account_currency is None:
        raise ValueError("Счет не найден")
    metadata = extract_statement_metadata(page_texts)
    parsed_rows, errors, rows_total = parse_statement_rows_from_page_texts(
        page_texts,
        bank_type=metadata.bank_type,
    )
    for row in parsed_rows:
        row.external_hash = make_external_hash(
            tx_date=row.tx_date,
            signed_amount=row.signed_amount,
            currency=row.currency,
            operation=row.operation,
            details=row.details,
            account_id=account_id,
        )

    if not parsed_rows:
        return PDFImportResult(
            rows_total=rows_total,
            inserted=0,
            skipped=0,
            errors=_truncate_errors(errors),
            account_id=account_id,
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
                status=row.status,
                account_id=account_id,
                import_id=import_id,
                category_id=0,
                tx_date=row.tx_date,
                source=TransactionSource.IMPORT_PDF,
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
            errors.append(f"Не удалось сохранить строку (стр. {row.page_no}): {exc}")

    currencies = {row.currency for row in parsed_rows}
    dates = [row.tx_date for row in parsed_rows]
    selected_currency = currencies.pop() if len(currencies) == 1 else account_currency
    closing_balance = None
    if selected_currency is not None:
        closing_balance = metadata.closing_balance_by_currency.get(selected_currency)
    if closing_balance is None and metadata.closing_balance_by_currency:
        closing_balance = next(iter(metadata.closing_balance_by_currency.values()))

    period_from = metadata.period_from or (min(dates) if dates else None)
    period_to = metadata.period_to or (max(dates) if dates else None)

    return PDFImportResult(
        rows_total=rows_total,
        inserted=inserted,
        skipped=skipped,
        errors=_truncate_errors(errors),
        account_id=account_id,
        period_from=period_from,
        period_to=period_to,
        currency=selected_currency,
        opening_balance=metadata.opening_balance,
        closing_balance=closing_balance,
        pending_balance=metadata.pending_balance,
    )
