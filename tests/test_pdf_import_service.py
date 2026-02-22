import datetime as dt
from decimal import Decimal

from app.models.enums import TransactionStatus, TransactionType
from app.services.pdf_import_service import (
    MAX_IMPORT_ERRORS,
    TABLE_HEADER,
    TABLE_HEADER_KASPI,
    extract_statement_metadata,
    deduplicate_rows,
    make_external_hash,
    parse_kaspi_statement_line,
    parse_statement_line,
    parse_statement_rows_from_page_texts,
)


def test_parse_kzt_row_with_comma_amount() -> None:
    row = parse_statement_line(
        "22.02.2026 -1,520.00 ₸ KZT Сумма в обработке IP AKTLEUOVA AD NUR-SULT N KZ",
        page_no=2,
    )

    assert row.tx_date == dt.date(2026, 2, 22)
    assert row.signed_amount == Decimal("-1520.00")
    assert row.amount == Decimal("1520.00")
    assert row.currency == "KZT"
    assert row.tx_type == TransactionType.EXPENSE
    assert row.status == TransactionStatus.PENDING
    assert row.operation == "Сумма в обработке"
    assert row.details == "IP AKTLEUOVA AD NUR-SULT N KZ"


def test_parse_usd_row_with_dot_amount() -> None:
    row = parse_statement_line(
        "06.02.2026 -14.48 $ USD Покупка Netflix.com Los Gatos NL",
        page_no=3,
    )

    assert row.tx_date == dt.date(2026, 2, 6)
    assert row.signed_amount == Decimal("-14.48")
    assert row.amount == Decimal("14.48")
    assert row.currency == "USD"
    assert row.tx_type == TransactionType.EXPENSE
    assert row.status == TransactionStatus.POSTED
    assert row.operation == "Покупка"
    assert row.details == "Netflix.com Los Gatos NL"


def test_multiline_details_are_joined() -> None:
    page_text = "\n".join(
        [
            "Выписка по карте",
            TABLE_HEADER,
            "06.02.2026 -14.48 $ USD Покупка Netflix.com",
            "Los Gatos NL",
            "19.02.2026 +203,210.00 ₸ KZT Пополнение Перевод с карты на карту",
        ]
    )

    rows, errors, total = parse_statement_rows_from_page_texts([page_text], bank_type="freedom")

    assert errors == []
    assert total == 2
    assert len(rows) == 2
    assert rows[0].details == "Netflix.com Los Gatos NL"


def test_deduplicate_by_external_hash() -> None:
    row1 = parse_statement_line("06.02.2026 -14.48 $ USD Покупка Netflix.com Los Gatos NL", page_no=2)
    row2 = parse_statement_line("06.02.2026 -14.48 $ USD Покупка Netflix.com Los Gatos NL", page_no=4)

    unique_rows, skipped = deduplicate_rows([row1, row2], existing_hashes=set())

    assert len(unique_rows) == 1
    assert skipped == 1


def test_extract_kaspi_header_balances() -> None:
    text = "\n".join(
        [
            "Kaspi Gold",
            "Доступно на 22.01.26 100,000.00 ₸",
            "Доступно на 22.02.26 120,500.00 ₸",
        ]
    )
    metadata = extract_statement_metadata([text])
    assert metadata.bank_type == "kaspi"
    assert metadata.opening_balance == Decimal("100000.00")
    assert metadata.closing_balance_by_currency["KZT"] == Decimal("120500.00")


def test_extract_kaspi_header_balances_with_amount_on_next_line() -> None:
    text = "\n".join(
        [
            "Kaspi Gold",
            "Доступно на 22.01.26",
            "100 000,00 ₸",
            "Доступно на 22.02.26",
            "120 500,00 ₸",
        ]
    )
    metadata = extract_statement_metadata([text])
    assert metadata.bank_type == "kaspi"
    assert metadata.opening_balance == Decimal("100000.00")
    assert metadata.closing_balance_by_currency["KZT"] == Decimal("120500.00")


def test_extract_freedom_header_pending_balance() -> None:
    text = "\n".join(
        [
            "Freedom Bank",
            "Остаток 450,000.00 ₸ KZT",
            "Остаток 120.50 $ USD",
            "Сумма в обработке 15,000.00",
        ]
    )
    metadata = extract_statement_metadata([text])
    assert metadata.bank_type == "freedom"
    assert metadata.closing_balance_by_currency["KZT"] == Decimal("450000.00")
    assert metadata.closing_balance_by_currency["USD"] == Decimal("120.50")
    assert metadata.pending_balance == Decimal("15000.00")


def test_kaspi_multiline_operation_joined_into_single_transaction() -> None:
    page_text = "\n".join(
        [
            "Kaspi Gold",
            TABLE_HEADER_KASPI,
            "21.02.26 - 5 863,00 ₸ Покупка",
            "YANDEX.EDA",
        ]
    )
    rows, errors, total = parse_statement_rows_from_page_texts([page_text], bank_type="kaspi")
    assert errors == []
    assert total == 1
    assert len(rows) == 1
    assert rows[0].operation == "Покупка"
    assert rows[0].details == "YANDEX.EDA"
    assert rows[0].description == "Покупка YANDEX.EDA"


def test_kaspi_supports_short_date_format_dd_mm_yy() -> None:
    row = parse_kaspi_statement_line("21.02.26 - 5 863,00 ₸ Покупка YANDEX.EDA", page_no=1)
    assert row.tx_date == dt.date(2026, 2, 21)


def test_kaspi_amount_with_spaces_and_comma_is_parsed() -> None:
    row = parse_kaspi_statement_line("21.02.26 - 5 863,00 ₸ Покупка YANDEX.EDA", page_no=1)
    assert row.amount == Decimal("5863.00")
    assert row.signed_amount == Decimal("-5863.00")
    assert row.currency == "KZT"
    assert row.tx_type == TransactionType.EXPENSE


def test_kaspi_transfer_details_can_be_on_next_line() -> None:
    page_text = "\n".join(
        [
            "Kaspi Gold",
            TABLE_HEADER_KASPI,
            "20.02.26 + 10 000,00 ₸ Перевод",
            "От ИП Шынгысов",
        ]
    )
    rows, errors, total = parse_statement_rows_from_page_texts([page_text], bank_type="kaspi")
    assert errors == []
    assert total == 1
    assert len(rows) == 1
    assert rows[0].operation == "Перевод"
    assert rows[0].details == "От ИП Шынгысов"
    assert rows[0].signed_amount == Decimal("10000.00")
    assert rows[0].tx_type == TransactionType.INCOME


def test_external_hash_depends_on_account_id() -> None:
    hash_a = make_external_hash(
        tx_date=dt.date(2026, 2, 21),
        signed_amount=Decimal("-5863.00"),
        currency="KZT",
        operation="Покупка",
        details="YANDEX.EDA",
        account_id=1,
    )
    hash_b = make_external_hash(
        tx_date=dt.date(2026, 2, 21),
        signed_amount=Decimal("-5863.00"),
        currency="KZT",
        operation="Покупка",
        details="YANDEX.EDA",
        account_id=2,
    )
    assert hash_a != hash_b


def test_errors_are_truncated_for_kaspi_parse() -> None:
    lines = ["Kaspi Gold", TABLE_HEADER_KASPI]
    lines.extend([f"21.02.26 невалидная строка {idx}" for idx in range(MAX_IMPORT_ERRORS + 5)])
    page_text = "\n".join(lines)
    rows, errors, total = parse_statement_rows_from_page_texts([page_text], bank_type="kaspi")
    assert rows == []
    assert total == MAX_IMPORT_ERRORS + 5
    assert len(errors) == MAX_IMPORT_ERRORS + 1
    assert errors[-1] == "и ещё 5 строк(и) с ошибками"
