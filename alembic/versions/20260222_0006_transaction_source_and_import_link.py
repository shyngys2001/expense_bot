"""transaction source enum and import link

Revision ID: 20260222_0006
Revises: 20260222_0005
Create Date: 2026-02-22 23:40:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260222_0006"
down_revision = "20260222_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_source') THEN
                CREATE TYPE transaction_source AS ENUM ('manual', 'import_pdf', 'import_csv', 'import_xlsx');
            END IF;
        END$$;
        """
    )

    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS import_id INTEGER;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tx_import_id ON transactions (import_id);")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transactions_import_id'
            ) THEN
                ALTER TABLE transactions
                ADD CONSTRAINT fk_transactions_import_id
                FOREIGN KEY (import_id) REFERENCES statement_imports(id) ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        ALTER TABLE transactions
        ALTER COLUMN source DROP DEFAULT;
        """
    )
    op.execute(
        """
        ALTER TABLE transactions
        ALTER COLUMN source TYPE transaction_source
        USING (
            CASE
                WHEN source IN ('manual', 'import_pdf', 'import_csv', 'import_xlsx') THEN source
                WHEN source = 'quick_add' THEN 'manual'
                ELSE 'manual'
            END
        )::transaction_source;
        """
    )
    op.execute("ALTER TABLE transactions ALTER COLUMN source SET DEFAULT 'manual';")
    op.execute("UPDATE transactions SET source = 'manual' WHERE source IS NULL;")
    op.execute("ALTER TABLE transactions ALTER COLUMN source SET NOT NULL;")


def downgrade() -> None:
    op.execute("ALTER TABLE transactions ALTER COLUMN source TYPE VARCHAR(32) USING source::text;")
    op.execute("ALTER TABLE transactions ALTER COLUMN source SET DEFAULT 'manual';")

    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_import_id;")
    op.execute("DROP INDEX IF EXISTS idx_tx_import_id;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS import_id;")

    op.execute("DROP TYPE IF EXISTS transaction_source;")
