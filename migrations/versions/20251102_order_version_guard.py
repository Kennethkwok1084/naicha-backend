"""ensure orders version column exists

Revision ID: 20251102_order_version_guard
Revises: 9a79aa03ff21
Create Date: 2025-11-02 10:30:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251102_order_version_guard"
down_revision = "9a79aa03ff21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0;
        """
    )
    op.execute("ALTER TABLE orders ALTER COLUMN version DROP DEFAULT;")


def downgrade() -> None:
    # 不回滚，保持与 9a79aa03ff21 相同的 orders 结构
    pass
