import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StatementImport(Base):
    __tablename__ = "statement_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="pdf", server_default="pdf")
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    imported_period_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    imported_period_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account = relationship("Account", back_populates="statement_imports")
