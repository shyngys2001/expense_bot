import datetime as dt
from decimal import Decimal

from app.models.enums import TransactionKind
from app.services.reporting import KindAmount, summarize_kind_amounts
from app.services.transfer_matcher import MatchableTransaction, build_candidate_pairs, choose_pairs


def _tx(
    tx_id: int,
    account_id: int,
    tx_date: dt.date,
    signed_amount: Decimal,
    currency: str = "KZT",
    description: str = "",
) -> MatchableTransaction:
    return MatchableTransaction(
        id=tx_id,
        account_id=account_id,
        tx_date=tx_date,
        currency=currency,
        signed_amount=signed_amount,
        description=description,
    )


def test_match_same_amount_same_day() -> None:
    transactions = [
        _tx(1, 1, dt.date(2026, 2, 10), Decimal("-10000"), description="Перевод на карту"),
        _tx(2, 2, dt.date(2026, 2, 10), Decimal("10000"), description="Пополнение с карты"),
    ]

    candidates, reviewed = build_candidate_pairs(transactions, window_days=1, tolerance=Decimal("0"))
    pairs = choose_pairs(candidates, threshold=80)

    assert reviewed == 1
    assert len(pairs) == 1
    assert pairs[0].expense_id == 1
    assert pairs[0].income_id == 2


def test_match_within_plus_minus_one_day() -> None:
    transactions = [
        _tx(1, 1, dt.date(2026, 2, 10), Decimal("-5000"), description="card to card"),
        _tx(2, 2, dt.date(2026, 2, 11), Decimal("5000"), description="freedom transfer"),
    ]

    candidates, _ = build_candidate_pairs(transactions, window_days=1, tolerance=Decimal("0"))
    pairs = choose_pairs(candidates, threshold=80)

    assert len(pairs) == 1
    assert pairs[0].date_delta_days == 1


def test_not_matched_when_currency_differs() -> None:
    transactions = [
        _tx(1, 1, dt.date(2026, 2, 10), Decimal("-14.48"), currency="USD", description="Перевод"),
        _tx(2, 2, dt.date(2026, 2, 10), Decimal("14.48"), currency="KZT", description="Пополнение"),
    ]

    candidates, reviewed = build_candidate_pairs(transactions, window_days=1, tolerance=Decimal("0"))
    pairs = choose_pairs(candidates, threshold=80)

    assert reviewed == 0
    assert pairs == []


def test_no_pair_keeps_income_regular() -> None:
    transactions = [
        _tx(1, 1, dt.date(2026, 2, 10), Decimal("120000"), description="Salary"),
    ]

    candidates, reviewed = build_candidate_pairs(transactions, window_days=1, tolerance=Decimal("0"))
    pairs = choose_pairs(candidates, threshold=80)

    assert reviewed == 0
    assert pairs == []


def test_conflict_resolves_to_best_candidate() -> None:
    transactions = [
        _tx(1, 1, dt.date(2026, 2, 10), Decimal("-10000"), description="Перевод kaspi"),
        _tx(2, 3, dt.date(2026, 2, 10), Decimal("-10000"), description="Покупка"),  # weaker
        _tx(3, 2, dt.date(2026, 2, 10), Decimal("10000"), description="Пополнение freedom"),
    ]

    candidates, _ = build_candidate_pairs(transactions, window_days=1, tolerance=Decimal("0"))
    pairs = choose_pairs(candidates, threshold=80)

    assert len(pairs) == 1
    assert pairs[0].expense_id == 1
    assert pairs[0].income_id == 3


def test_reports_do_not_count_transfer_as_income_or_expense() -> None:
    total_income, total_expense, total_transfers = summarize_kind_amounts(
        [
            KindAmount(kind=TransactionKind.INCOME, signed_amount=Decimal("1000")),
            KindAmount(kind=TransactionKind.EXPENSE, signed_amount=Decimal("-250")),
            KindAmount(kind=TransactionKind.TRANSFER, signed_amount=Decimal("-400")),
            KindAmount(kind=TransactionKind.TRANSFER, signed_amount=Decimal("400")),
        ]
    )

    assert total_income == Decimal("1000")
    assert total_expense == Decimal("250")
    assert total_transfers == Decimal("400")
