import datetime as dt
from decimal import Decimal

from app.models.enums import TransactionType
from app.services.pdf_import_service import (
    TABLE_HEADER,
    deduplicate_rows,
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

    rows, errors, total = parse_statement_rows_from_page_texts([page_text])

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
