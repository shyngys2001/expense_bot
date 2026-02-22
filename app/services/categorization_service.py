from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.enums import RuleMatchType, TransactionType
from app.models.transaction import Transaction


@dataclass(slots=True)
class RuleCandidate:
    pattern: str
    match_type: RuleMatchType
    category_id: int
    priority: int
    created_at: datetime
    is_active: bool


def normalize_text(text: str) -> str:
    lowered = text.lower().replace("\xa0", " ")
    normalized = re.sub(r"[\.,]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def rule_matches(rule: RuleCandidate, normalized_description: str) -> bool:
    if not rule.is_active:
        return False

    if rule.match_type == RuleMatchType.CONTAINS:
        return normalize_text(rule.pattern) in normalized_description

    if rule.match_type == RuleMatchType.REGEX:
        try:
            return re.search(rule.pattern, normalized_description, flags=re.IGNORECASE) is not None
        except re.error:
            return False

    return False


def choose_best_category(normalized_description: str, rules: list[RuleCandidate]) -> int | None:
    matched = [rule for rule in rules if rule_matches(rule, normalized_description)]
    if not matched:
        return None

    matched.sort(key=lambda item: (item.priority, item.created_at), reverse=True)
    return matched[0].category_id


async def find_category_for(session: AsyncSession, description: str, tx_type: TransactionType) -> int:
    normalized_description = normalize_text(description)

    rows = await session.scalars(
        select(CategoryRule)
        .join(Category, CategoryRule.category_id == Category.id)
        .where(Category.type == tx_type, CategoryRule.is_active.is_(True))
        .order_by(CategoryRule.priority.desc(), CategoryRule.created_at.desc())
    )

    rules = [
        RuleCandidate(
            pattern=rule.pattern,
            match_type=rule.match_type,
            category_id=rule.category_id,
            priority=rule.priority,
            created_at=rule.created_at,
            is_active=rule.is_active,
        )
        for rule in rows
    ]

    chosen_category = choose_best_category(normalized_description, rules)
    if chosen_category is not None:
        return chosen_category

    other_category = await session.scalar(
        select(Category.id).where(Category.name == "Other", Category.type == tx_type)
    )
    if other_category is None:
        raise RuntimeError("Default category 'Other' not found")

    return other_category


async def apply_category(session: AsyncSession, transaction: Transaction) -> int:
    if transaction.category_locked:
        return transaction.category_id

    category_id = await find_category_for(session, transaction.description, transaction.type)
    transaction.category_id = category_id
    return category_id
