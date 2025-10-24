"""add unique constraint for print_jobs order relationship

Revision ID: 20251024_0001
Revises: 20251022_0003
Create Date: 2025-10-24 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251024_0001"
down_revision = "20251022_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_print_jobs_order_id",
        "print_jobs",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_print_jobs_order_id", "print_jobs", type_="unique")
