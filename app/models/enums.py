from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionKind(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class RuleMatchType(str, Enum):
    CONTAINS = "contains"
    REGEX = "regex"


transaction_type_enum = ENUM(
    TransactionType,
    name="transaction_type",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

transaction_kind_enum = ENUM(
    TransactionKind,
    name="transaction_kind",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)
