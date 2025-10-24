"""add stock quantity column to products

Revision ID: 20251024_0002
Revises: 20251024_0001
Create Date: 2025-10-24 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251024_0002"
down_revision = "20251024_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_products_stock_quantity_non_negative",
        "products",
        "stock_quantity >= 0",
    )
    op.execute(
        """
        UPDATE products
        SET stock_quantity = CASE
            WHEN inventory_status = 'in_stock' THEN 100000
            ELSE 0
        END
        """
    )
    op.alter_column("products", "stock_quantity", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_products_stock_quantity_non_negative",
        "products",
        type_="check",
    )
    op.drop_column("products", "stock_quantity")
