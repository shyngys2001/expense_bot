"""autocategorization rules engine

Revision ID: 20260222_0003
Revises: 20260222_0002
Create Date: 2026-02-22 22:00:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260222_0003"
down_revision = "20260222_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'category_rules' AND column_name = 'keyword'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'category_rules' AND column_name = 'pattern'
            ) THEN
                ALTER TABLE category_rules RENAME COLUMN keyword TO pattern;
            END IF;
        END$$;
        """
    )

    op.execute("ALTER TABLE category_rules DROP CONSTRAINT IF EXISTS category_rules_keyword_key;")
    op.execute("ALTER TABLE category_rules DROP CONSTRAINT IF EXISTS category_rules_pattern_key;")
    op.execute("DROP INDEX IF EXISTS ix_category_rules_keyword;")
    op.execute("ALTER TABLE category_rules ALTER COLUMN pattern TYPE VARCHAR(255);")

    op.execute(
        "ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS match_type VARCHAR(16) NOT NULL DEFAULT 'contains';"
    )
    op.execute(
        "ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;"
    )
    op.execute(
        "ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;"
    )
    op.execute(
        "ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_category_rules_priority ON category_rules (priority DESC, created_at DESC);"
    )

    op.execute(
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_locked BOOLEAN NOT NULL DEFAULT FALSE;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transactions_description_lower ON transactions (lower(description));"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transactions_description_lower;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS category_locked;")

    op.execute("DROP INDEX IF EXISTS ix_category_rules_priority;")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS created_at;")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS is_active;")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS priority;")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS match_type;")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'category_rules' AND column_name = 'pattern'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'category_rules' AND column_name = 'keyword'
            ) THEN
                ALTER TABLE category_rules RENAME COLUMN pattern TO keyword;
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'category_rules_keyword_key'
            ) THEN
                ALTER TABLE category_rules ADD CONSTRAINT category_rules_keyword_key UNIQUE(keyword);
            END IF;
        END$$;
        """
    )
