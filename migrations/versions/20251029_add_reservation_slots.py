"""add reservation slots table and link orders

Revision ID: 20251029_add_reservation_slots
Revises: 20251028_add_maintenance_jobs
Create Date: 2025-10-29 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251029_add_reservation_slots"
down_revision = "20251028_add_maintenance_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservation_slots",
        sa.Column("slot_id", sa.BigInteger(), primary_key=True),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("reserved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "capacity > 0",
            name="ck_reservation_slots_capacity_positive",
        ),
        sa.CheckConstraint(
            "reserved_count >= 0",
            name="ck_reservation_slots_reserved_count_non_negative",
        ),
        sa.UniqueConstraint("slot_start", name="uq_reservation_slots_start"),
    )

    op.add_column(
        "orders",
        sa.Column("reservation_slot_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_reservation_slot_id_reservation_slots",
        "orders",
        "reservation_slots",
        ["reservation_slot_id"],
        ["slot_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_orders_reservation_slot_id_reservation_slots",
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "reservation_slot_id")
    op.drop_table("reservation_slots")
