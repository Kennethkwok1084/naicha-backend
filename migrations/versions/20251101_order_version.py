"""add optimistic locking column to orders

Revision ID: 20251101_order_version
Revises: 20251029_add_reservation_slots
Create Date: 2025-11-01 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251101_order_version"
down_revision = "20251029_add_reservation_slots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("orders", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "version")
