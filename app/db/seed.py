from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.enums import RuleMatchType, TransactionType
from app.services.accounts import DEFAULT_ACCOUNT_NAME, LEGACY_DEFAULT_ACCOUNT_NAME

REQUIRED_EXPENSE_CATEGORIES: Sequence[str] = (
    "Food",
    "Transport",
    "Home",
    "Health",
    "Entertainment",
    "Subscriptions",
    "Transfers",
    "Other",
)

REQUIRED_INCOME_CATEGORIES: Sequence[str] = (
    "Salary",
    "Gift",
    "Other",
)

DEFAULT_RULES: Sequence[tuple[str, RuleMatchType, str, TransactionType, int]] = (
    ("yandex.eda", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 100),
    ("yandex eda", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 100),
    ("yandex.go", RuleMatchType.CONTAINS, "Transport", TransactionType.EXPENSE, 100),
    ("yandex go", RuleMatchType.CONTAINS, "Transport", TransactionType.EXPENSE, 100),
    ("ip dzhumagulov", RuleMatchType.CONTAINS, "Entertainment", TransactionType.EXPENSE, 90),
    ("netflix", RuleMatchType.CONTAINS, "Subscriptions", TransactionType.EXPENSE, 90),
    ("minimarket", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 80),
    ("magnum", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 80),
    ("kaspi", RuleMatchType.CONTAINS, "Transfers", TransactionType.EXPENSE, 70),
    ("freedom", RuleMatchType.CONTAINS, "Transfers", TransactionType.EXPENSE, 70),
    ("bank transfer", RuleMatchType.CONTAINS, "Transfers", TransactionType.EXPENSE, 70),
    ("кофе", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 60),
    ("coffee", RuleMatchType.CONTAINS, "Food", TransactionType.EXPENSE, 60),
    ("такси", RuleMatchType.CONTAINS, "Transport", TransactionType.EXPENSE, 60),
    ("taxi", RuleMatchType.CONTAINS, "Transport", TransactionType.EXPENSE, 60),
    ("зарплата", RuleMatchType.CONTAINS, "Salary", TransactionType.INCOME, 90),
    ("salary", RuleMatchType.CONTAINS, "Salary", TransactionType.INCOME, 90),
)


async def _ensure_categories(session: AsyncSession) -> dict[tuple[str, TransactionType], Category]:
    rows = await session.scalars(select(Category))
    existing = {(category.name, category.type): category for category in rows}

    for name in REQUIRED_EXPENSE_CATEGORIES:
        key = (name, TransactionType.EXPENSE)
        if key not in existing:
            category = Category(name=name, type=TransactionType.EXPENSE)
            session.add(category)
            existing[key] = category

    for name in REQUIRED_INCOME_CATEGORIES:
        key = (name, TransactionType.INCOME)
        if key not in existing:
            category = Category(name=name, type=TransactionType.INCOME)
            session.add(category)
            existing[key] = category

    await session.flush()

    rows = await session.scalars(select(Category))
    return {(category.name, category.type): category for category in rows}


async def _ensure_rules(
    session: AsyncSession,
    categories: dict[tuple[str, TransactionType], Category],
) -> None:
    existing_rules_rows = await session.scalars(select(CategoryRule))
    existing_keys = {
        (
            rule.pattern.lower(),
            rule.match_type,
            rule.category_id,
        )
        for rule in existing_rules_rows
    }

    for pattern, match_type, category_name, tx_type, priority in DEFAULT_RULES:
        category = categories.get((category_name, tx_type))
        if category is None:
            continue

        key = (pattern.lower(), match_type, category.id)
        if key in existing_keys:
            continue

        session.add(
            CategoryRule(
                pattern=pattern,
                match_type=match_type,
                category_id=category.id,
                priority=priority,
                is_active=True,
            )
        )


async def seed_initial_data(session: AsyncSession, seed_demo: bool = False) -> None:
    _ = seed_demo
    account = await session.scalar(select(Account).where(Account.name == DEFAULT_ACCOUNT_NAME))
    if account is None:
        account = await session.scalar(select(Account).where(Account.name == LEGACY_DEFAULT_ACCOUNT_NAME))
    if account is None:
        session.add(Account(name=DEFAULT_ACCOUNT_NAME, bank="Не указан", currency="KZT", is_active=True))

    categories = await _ensure_categories(session)
    await _ensure_rules(session, categories)
    await session.commit()
