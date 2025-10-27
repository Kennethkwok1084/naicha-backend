"""add coupon_id to orders table

Revision ID: 20251027_add_coupon_id
Revises: 20251102_order_version_guard
Create Date: 2025-10-27 22:50:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251027_add_coupon_id"
down_revision = "20251102_order_version_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("coupon_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_orders_coupon_id_coupons"),
        "orders",
        "coupons",
        ["coupon_id"],
        ["coupon_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_orders_coupon_id_coupons"), "orders", type_="foreignkey")
    op.drop_column("orders", "coupon_id")
