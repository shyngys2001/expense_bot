from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionKind(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransactionStatus(str, Enum):
    POSTED = "posted"
    PENDING = "pending"


class TransactionSource(str, Enum):
    MANUAL = "manual"
    IMPORT_PDF = "import_pdf"
    IMPORT_CSV = "import_csv"
    IMPORT_XLSX = "import_xlsx"


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

transaction_status_enum = ENUM(
    TransactionStatus,
    name="transaction_status",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

transaction_source_enum = ENUM(
    TransactionSource,
    name="transaction_source",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)
