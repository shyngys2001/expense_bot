"""balances metadata and transaction status

Revision ID: 20260222_0005
Revises: 20260222_0004
Create Date: 2026-02-22 23:50:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260222_0005"
down_revision = "20260222_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_status') THEN
                CREATE TYPE transaction_status AS ENUM ('posted', 'pending');
            END IF;
        END$$;
        """
    )

    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS status transaction_status;")
    op.execute(
        """
        UPDATE transactions
        SET status = CASE
            WHEN lower(description) LIKE '%в обработке%'
                 OR COALESCE(raw ->> 'operation', '') ILIKE '%Сумма в обработке%'
            THEN 'pending'::transaction_status
            ELSE 'posted'::transaction_status
        END
        WHERE status IS NULL;
        """
    )
    op.execute("ALTER TABLE transactions ALTER COLUMN status SET NOT NULL;")
    op.execute("ALTER TABLE transactions ALTER COLUMN status SET DEFAULT 'posted';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions (status);")

    op.execute("ALTER TABLE statement_imports ADD COLUMN IF NOT EXISTS period_from DATE;")
    op.execute("ALTER TABLE statement_imports ADD COLUMN IF NOT EXISTS period_to DATE;")
    op.execute("ALTER TABLE statement_imports ADD COLUMN IF NOT EXISTS opening_balance NUMERIC(14,2);")
    op.execute("ALTER TABLE statement_imports ADD COLUMN IF NOT EXISTS closing_balance NUMERIC(14,2);")
    op.execute("ALTER TABLE statement_imports ADD COLUMN IF NOT EXISTS pending_balance NUMERIC(14,2);")

    op.execute(
        """
        UPDATE statement_imports
        SET period_from = imported_period_from
        WHERE period_from IS NULL AND imported_period_from IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE statement_imports
        SET period_to = imported_period_to
        WHERE period_to IS NULL AND imported_period_to IS NOT NULL;
        """
    )

    op.execute(
        """
        UPDATE accounts
        SET name = 'Основной счет'
        WHERE name = 'Main Account'
          AND NOT EXISTS (SELECT 1 FROM accounts WHERE name = 'Основной счет');
        """
    )
    op.execute("UPDATE accounts SET bank = 'Не указан' WHERE bank = 'Unknown';")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tx_status;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS status;")

    op.execute("ALTER TABLE statement_imports DROP COLUMN IF EXISTS pending_balance;")
    op.execute("ALTER TABLE statement_imports DROP COLUMN IF EXISTS closing_balance;")
    op.execute("ALTER TABLE statement_imports DROP COLUMN IF EXISTS opening_balance;")
    op.execute("ALTER TABLE statement_imports DROP COLUMN IF EXISTS period_to;")
    op.execute("ALTER TABLE statement_imports DROP COLUMN IF EXISTS period_from;")

    op.execute("DROP TYPE IF EXISTS transaction_status;")
