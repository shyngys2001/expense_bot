from decimal import Decimal

import pytest

from app.models.enums import TransactionType
from app.services.quick_add import parse_quick_add_text


def test_parse_expense_quick_add() -> None:
    parsed = parse_quick_add_text("кофе 1200")

    assert parsed.description == "кофе"
    assert parsed.amount == Decimal("1200")
    assert parsed.tx_type == TransactionType.EXPENSE
    assert parsed.currency == "KZT"


def test_parse_income_quick_add() -> None:
    parsed = parse_quick_add_text("зарплата +500000")

    assert parsed.description == "зарплата"
    assert parsed.amount == Decimal("500000")
    assert parsed.tx_type == TransactionType.INCOME


def test_parse_quick_add_without_amount_raises_error() -> None:
    with pytest.raises(ValueError, match="Не найдена сумма"):
        parse_quick_add_text("просто текст")
