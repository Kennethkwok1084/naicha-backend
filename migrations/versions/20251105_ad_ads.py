"""添加广告位、素材与投放关联表

Revision ID: 20251105_ad_ads
Revises: 20251102_order_version_guard
Create Date: 2025-11-05 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251105_ad_ads"
down_revision = "20251102_order_version_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_slots",
        sa.Column("slot_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "spec",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "ad_creatives",
        sa.Column("creative_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("jump_type", sa.String(length=20), nullable=False),
        sa.Column("jump_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "platforms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
            "jump_type IN ('miniapp_page','h5','none')",
            name="ck_ad_creatives_jump_type",
        ),
    )
    op.create_index(
        "ix_ad_creatives_enabled_priority",
        "ad_creatives",
        ["enabled", "priority"],
        unique=False,
    )

    op.create_table(
        "ad_placements",
        sa.Column("placement_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "slot_code",
            sa.String(length=50),
            sa.ForeignKey("ad_slots.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "creative_id",
            sa.BigInteger(),
            sa.ForeignKey("ad_creatives.creative_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
        sa.UniqueConstraint(
            "slot_code",
            "creative_id",
            name="uq_ad_placements_slot_creative",
        ),
    )
    op.create_index("ix_ad_placements_slot_code", "ad_placements", ["slot_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ad_placements_slot_code", table_name="ad_placements")
    op.drop_table("ad_placements")
    op.drop_index("ix_ad_creatives_enabled_priority", table_name="ad_creatives")
    op.drop_table("ad_creatives")
    op.drop_table("ad_slots")
