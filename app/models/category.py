from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TransactionType, transaction_type_enum


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "type", name="uq_categories_name_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[TransactionType] = mapped_column(transaction_type_enum, nullable=False)

    rules = relationship("CategoryRule", back_populates="category", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="category")
