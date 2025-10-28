"""Merge coupon and advertisement heads

Revision ID: 20251106_merge_ads
Revises: 20251027_add_coupon_id, 20251105_ad_ads
Create Date: 2025-11-06 00:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20251106_merge_ads"
down_revision = ("20251027_add_coupon_id", "20251105_ad_ads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
