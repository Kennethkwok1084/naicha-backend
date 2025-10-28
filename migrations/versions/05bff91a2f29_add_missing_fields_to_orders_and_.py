"""add missing fields to orders and payment_records

Revision ID: 05bff91a2f29
Revises: 20251029_add_reservation_slots
Create Date: 2025-10-26 01:46:10.843470
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '05bff91a2f29'
down_revision = '20251101_order_version'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.create_check_constraint(
        "ck_orders_source",
        "orders",
        "source IN ('user','pos','system')",
    )
    op.add_column(
        "orders",
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_created_by_admin_id_admins",
        "orders",
        "admins",
        ["created_by_admin_id"],
        ["admin_id"],
    )
    op.add_column(
        "payment_records",
        sa.Column("qr_session_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_payment_records_qr_session_status",
        "payment_records",
        ["qr_session_id", "match_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_records_qr_session_status", table_name="payment_records")
    op.drop_column("payment_records", "qr_session_id")
    op.drop_constraint(
        "fk_orders_created_by_admin_id_admins",
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "created_by_admin_id")
    op.drop_constraint("ck_orders_source", "orders", type_="check")
    op.drop_column("orders", "source")
