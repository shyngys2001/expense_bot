from app.models.transaction import Transaction
from app.schemas.transaction import TransactionRead


def serialize_transaction(transaction: Transaction) -> TransactionRead:
    category_name = transaction.category.name if transaction.category else "Unknown"
    account_name = transaction.account.name if transaction.account else "Unknown"
    matched_account_name = transaction.matched_account.name if transaction.matched_account else None
    return TransactionRead(
        id=transaction.id,
        description=transaction.description,
        amount=transaction.amount,
        signed_amount=transaction.signed_amount,
        currency=transaction.currency,
        type=transaction.type,
        kind=transaction.kind,
        account_id=transaction.account_id,
        account_name=account_name,
        category_id=transaction.category_id,
        category_name=category_name,
        category_locked=transaction.category_locked,
        transfer_pair_id=transaction.transfer_pair_id,
        matched_account_id=transaction.matched_account_id,
        matched_account_name=matched_account_name,
        match_confidence=transaction.match_confidence,
        source=transaction.source,
        tx_date=transaction.tx_date,
        posted_at=transaction.posted_at,
        created_at=transaction.created_at,
    )
