import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.enums import RuleMatchType, TransactionType
from app.services import categorization_service
from app.services.categorization_service import RuleCandidate, choose_best_category, normalize_text, rule_matches


def test_normalize_text_unifies_case_and_punctuation() -> None:
    assert normalize_text("YANDEX.GO") == normalize_text("yandex go")


def test_contains_rule_matches() -> None:
    description = normalize_text("Покупка Yandex.Go taxi")
    rule = RuleCandidate(
        pattern="yandex go",
        match_type=RuleMatchType.CONTAINS,
        category_id=10,
        priority=100,
        created_at=datetime.now(tz=timezone.utc),
        is_active=True,
    )

    assert rule_matches(rule, description)


def test_regex_rule_matches() -> None:
    description = normalize_text("Подписка netflix.com")
    rule = RuleCandidate(
        pattern=r"\bnetflix\b",
        match_type=RuleMatchType.REGEX,
        category_id=15,
        priority=90,
        created_at=datetime.now(tz=timezone.utc),
        is_active=True,
    )

    assert rule_matches(rule, description)


def test_choose_rule_with_higher_priority() -> None:
    description = normalize_text("Покупка yandex go")
    low_priority = RuleCandidate(
        pattern="yandex",
        match_type=RuleMatchType.CONTAINS,
        category_id=1,
        priority=50,
        created_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
        is_active=True,
    )
    high_priority = RuleCandidate(
        pattern="yandex go",
        match_type=RuleMatchType.CONTAINS,
        category_id=2,
        priority=100,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        is_active=True,
    )

    result = choose_best_category(description, [low_priority, high_priority])

    assert result == 2


def test_locked_category_not_overwritten(monkeypatch) -> None:
    transaction = SimpleNamespace(
        description="yandex go",
        type=TransactionType.EXPENSE,
        category_id=99,
        category_locked=True,
    )

    called = False

    async def fake_find_category_for(session, description, tx_type):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr(categorization_service, "find_category_for", fake_find_category_for)

    resolved = asyncio.run(categorization_service.apply_category(None, transaction))

    assert resolved == 99
    assert transaction.category_id == 99
    assert called is False
