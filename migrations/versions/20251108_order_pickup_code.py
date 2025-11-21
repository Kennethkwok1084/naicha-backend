"""为订单新增取餐码列

Revision ID: 20251108_order_pickup_code
Revises: 20251108_shop_cfg_flags
Create Date: 2025-11-08 15:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251108_order_pickup_code"
down_revision = "20251108_shop_cfg_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("pickup_code", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "pickup_code")
