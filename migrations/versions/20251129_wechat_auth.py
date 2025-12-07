"""Add WeChat authentication tables

Revision ID: 20251129_wechat_auth
Revises: 5c34c68b9b8c
Create Date: 2025-11-29 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251129_wechat_auth"
down_revision = "5c34c68b9b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加users表的新字段
    op.add_column("users", sa.Column("union_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=30), nullable=True))
    op.create_index("ix_users_union_id", "users", ["union_id"])
    op.create_index("ix_users_phone", "users", ["phone"])
    
    # 创建wechat_used_codes表
    op.create_table(
        "wechat_used_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("code_type", sa.String(length=20), nullable=False),
        sa.Column("used_by_openid", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("code_type IN ('login','phone')", name="ck_wechat_used_codes_type"),
    )
    op.create_index("ix_wechat_used_codes_code_hash", "wechat_used_codes", ["code_hash"])
    op.create_index("ix_wechat_used_codes_created", "wechat_used_codes", ["created_at"])
    
    # 创建token_blacklist表
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("token_jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_token_blacklist_token_jti", "token_blacklist", ["token_jti"])
    op.create_index("ix_token_blacklist_user_id", "token_blacklist", ["user_id"])
    op.create_index("ix_token_blacklist_expires", "token_blacklist", ["expires_at"])


def downgrade() -> None:
    # 删除token_blacklist表
    op.drop_index("ix_token_blacklist_expires", "token_blacklist")
    op.drop_index("ix_token_blacklist_user_id", "token_blacklist")
    op.drop_index("ix_token_blacklist_token_jti", "token_blacklist")
    op.drop_table("token_blacklist")
    
    # 删除wechat_used_codes表
    op.drop_index("ix_wechat_used_codes_created", "wechat_used_codes")
    op.drop_index("ix_wechat_used_codes_code_hash", "wechat_used_codes")
    op.drop_table("wechat_used_codes")
    
    # 删除users表的新字段
    op.drop_index("ix_users_phone", "users")
    op.drop_index("ix_users_union_id", "users")
    op.drop_column("users", "phone")
    op.drop_column("users", "union_id")
