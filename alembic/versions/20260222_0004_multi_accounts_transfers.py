"""multi accounts and transfer matching fields

Revision ID: 20260222_0004
Revises: 20260222_0003
Create Date: 2026-02-22 23:20:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260222_0004"
down_revision = "20260222_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_kind') THEN
                CREATE TYPE transaction_kind AS ENUM ('income', 'expense', 'transfer');
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            bank VARCHAR(100) NOT NULL DEFAULT 'Unknown',
            currency VARCHAR(3) NOT NULL DEFAULT 'KZT',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        INSERT INTO accounts(name, bank, currency, is_active)
        SELECT 'Main Account', 'Unknown', 'KZT', TRUE
        WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE name = 'Main Account');
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS statement_imports (
            id SERIAL PRIMARY KEY,
            source VARCHAR(32) NOT NULL DEFAULT 'pdf',
            filename VARCHAR(255),
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            currency VARCHAR(3),
            imported_period_from DATE,
            imported_period_to DATE,
            rows_total INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS account_id INTEGER;")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS kind transaction_kind;")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS signed_amount NUMERIC(12,2);")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS transfer_pair_id UUID;")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS matched_account_id INTEGER;")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS match_confidence INTEGER;")

    op.execute(
        """
        UPDATE transactions
        SET account_id = (
            SELECT id FROM accounts WHERE name = 'Main Account' ORDER BY id LIMIT 1
        )
        WHERE account_id IS NULL;
        """
    )
    op.execute(
        """
        UPDATE transactions
        SET signed_amount = CASE
            WHEN type = 'income' THEN amount
            ELSE amount * -1
        END
        WHERE signed_amount IS NULL;
        """
    )
    op.execute(
        """
        UPDATE transactions
        SET kind = CASE
            WHEN type = 'income' THEN 'income'::transaction_kind
            ELSE 'expense'::transaction_kind
        END
        WHERE kind IS NULL;
        """
    )

    op.execute("ALTER TABLE transactions ALTER COLUMN account_id SET NOT NULL;")
    op.execute("ALTER TABLE transactions ALTER COLUMN signed_amount SET NOT NULL;")
    op.execute("ALTER TABLE transactions ALTER COLUMN kind SET NOT NULL;")
    op.execute("ALTER TABLE transactions ALTER COLUMN kind SET DEFAULT 'expense';")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transactions_account_id'
            ) THEN
                ALTER TABLE transactions
                ADD CONSTRAINT fk_transactions_account_id
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT;
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_transactions_matched_account_id'
            ) THEN
                ALTER TABLE transactions
                ADD CONSTRAINT fk_transactions_matched_account_id
                FOREIGN KEY (matched_account_id) REFERENCES accounts(id) ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_transactions_match_confidence'
            ) THEN
                ALTER TABLE transactions
                ADD CONSTRAINT ck_transactions_match_confidence
                CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 100));
            END IF;
        END$$;
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_lookup ON transactions (account_id, tx_date, currency, signed_amount);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tx_kind ON transactions (kind);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tx_pair ON transactions (transfer_pair_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tx_pair;")
    op.execute("DROP INDEX IF EXISTS idx_tx_kind;")
    op.execute("DROP INDEX IF EXISTS idx_tx_lookup;")

    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS ck_transactions_match_confidence;")
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_matched_account_id;")
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_account_id;")

    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS match_confidence;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS matched_account_id;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS transfer_pair_id;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS signed_amount;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS kind;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS posted_at;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS account_id;")

    op.execute("DROP TABLE IF EXISTS statement_imports;")
    op.execute("DROP TABLE IF EXISTS accounts;")
    op.execute("DROP TYPE IF EXISTS transaction_kind;")
