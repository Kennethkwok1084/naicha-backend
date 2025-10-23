"""add payment_record match columns

Revision ID: 20251022_0003
Revises: 20251022_0002
Create Date: 2025-10-22 23:35:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251022_0003"
down_revision = "20251022_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "payment_records",
        sa.Column("matched_by_admin_id", sa.BigInteger(), sa.ForeignKey("admins.admin_id"), nullable=True),
    )
    op.add_column(
        "payment_records",
        sa.Column("match_confidence", sa.Numeric(5, 4), nullable=True),
    )


def downgrade():
    op.drop_column("payment_records", "match_confidence")
    op.drop_column("payment_records", "matched_by_admin_id")
