import datetime as dt

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    bank: Mapped[str] = mapped_column(String(100), nullable=False, default="Не указан", server_default="Не указан")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KZT", server_default="KZT")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    transactions = relationship(
        "Transaction",
        back_populates="account",
        foreign_keys="Transaction.account_id",
    )
    matched_transactions = relationship(
        "Transaction",
        back_populates="matched_account",
        foreign_keys="Transaction.matched_account_id",
    )
    statement_imports = relationship("StatementImport", back_populates="account")
