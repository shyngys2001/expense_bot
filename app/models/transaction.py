import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    TransactionKind,
    TransactionSource,
    TransactionStatus,
    TransactionType,
    transaction_kind_enum,
    transaction_source_enum,
    transaction_status_enum,
    transaction_type_enum,
)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    signed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KZT", server_default="KZT")
    type: Mapped[TransactionType] = mapped_column(transaction_type_enum, nullable=False)
    kind: Mapped[TransactionKind] = mapped_column(
        transaction_kind_enum,
        nullable=False,
        default=TransactionKind.EXPENSE,
        server_default=TransactionKind.EXPENSE.value,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        transaction_status_enum,
        nullable=False,
        default=TransactionStatus.POSTED,
        server_default=TransactionStatus.POSTED.value,
    )
    source: Mapped[TransactionSource] = mapped_column(
        transaction_source_enum,
        nullable=False,
        default=TransactionSource.MANUAL,
        server_default=TransactionSource.MANUAL.value,
    )
    external_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    transfer_pair_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    match_confidence: Mapped[int | None] = mapped_column(nullable=True)
    category_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    tx_date: Mapped[dt.date] = mapped_column(Date, nullable=False, default=dt.date.today, server_default=func.current_date())
    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("statement_imports.id", ondelete="SET NULL"), nullable=True)
    matched_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)

    category = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions", foreign_keys=[account_id])
    statement_import = relationship("StatementImport", back_populates="transactions")
    matched_account = relationship("Account", back_populates="matched_transactions", foreign_keys=[matched_account_id])
