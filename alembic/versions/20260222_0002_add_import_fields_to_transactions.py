"""add import fields to transactions

Revision ID: 20260222_0002
Revises: 20260222_0001
Create Date: 2026-02-22 20:40:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260222_0002"
down_revision = "20260222_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "transactions",
        sa.Column("external_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(
        "uq_transactions_external_hash",
        "transactions",
        ["external_hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_transactions_external_hash", "transactions", type_="unique")
    op.drop_column("transactions", "raw")
    op.drop_column("transactions", "external_hash")
    op.drop_column("transactions", "source")
