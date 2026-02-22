import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.models.enums import TransactionType

NUMBER_PATTERN = re.compile(r"([+-]?\d+(?:[\.,]\d+)?)")


@dataclass(slots=True)
class ParsedQuickAdd:
    description: str
    amount: Decimal
    tx_type: TransactionType
    currency: str = "KZT"


def parse_quick_add_text(text: str) -> ParsedQuickAdd:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Input text is empty")

    matches = list(NUMBER_PATTERN.finditer(cleaned))
    if not matches:
        raise ValueError("Amount is missing")

    amount_match = matches[-1]
    raw_amount = amount_match.group(1).replace(",", ".")

    try:
        amount = Decimal(raw_amount.lstrip("+-"))
    except InvalidOperation as exc:
        raise ValueError("Amount format is invalid") from exc

    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    description = (cleaned[: amount_match.start()] + cleaned[amount_match.end() :]).strip()
    description = re.sub(r"\s+", " ", description).strip("+- ")
    if not description:
        description = "Transaction"

    tx_type = TransactionType.INCOME if "+" in cleaned else TransactionType.EXPENSE

    return ParsedQuickAdd(description=description, amount=amount, tx_type=tx_type)
