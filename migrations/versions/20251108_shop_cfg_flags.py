"""新增门店功能开关配置表

Revision ID: 20251108_shop_cfg_flags
Revises: 20251106_merge_ads
Create Date: 2025-11-08 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251108_shop_cfg_flags"
down_revision = "20251106_merge_ads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_config",
        sa.Column("config_key", sa.String(length=50), primary_key=True),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "category",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'features'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admins.admin_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_shop_config_category",
        "shop_config",
        ["category"],
        unique=False,
    )

    shop_config_table = sa.table(
        "shop_config",
        sa.column("config_key", sa.String()),
        sa.column("value_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        shop_config_table,
        [
            {
                "config_key": "features.disable_delivery",
                "value_json": False,
                "category": "features",
                "description": "紧急关闭外卖配送",
            },
            {
                "config_key": "features.disable_coupons",
                "value_json": False,
                "category": "features",
                "description": "临时关闭优惠券功能",
            },
            {
                "config_key": "features.disable_stamps",
                "value_json": False,
                "category": "features",
                "description": "临时关闭集点功能",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_shop_config_category", table_name="shop_config")
    op.drop_table("shop_config")
