"""init tables

Revision ID: 20260222_0001
Revises:
Create Date: 2026-02-22 19:40:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260222_0001"
down_revision = None
branch_labels = None
depends_on = None


transaction_type_enum = postgresql.ENUM(
    "income",
    "expense",
    name="transaction_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_type') THEN
                CREATE TYPE transaction_type AS ENUM ('income', 'expense');
            END IF;
        END$$;
        """
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.UniqueConstraint("name", "type", name="uq_categories_name_type"),
    )

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("keyword"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KZT"),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.Column("tx_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("category_rules")
    op.drop_table("categories")
    op.execute("DROP TYPE IF EXISTS transaction_type;")
