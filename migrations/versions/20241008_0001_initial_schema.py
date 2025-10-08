"""Initial schema for Naicha backend.

Revision ID: 20241008_0001
Revises: None
Create Date: 2025-10-08 22:25:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20241008_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_settings",
        sa.Column("key", sa.String(length=50), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "shop_profile",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default=sa.text("1")),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("open_hours_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("location_lat", sa.Float(precision=53), nullable=True),
        sa.Column("location_lng", sa.Float(precision=53), nullable=True),
        sa.Column("delivery_radius_m", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 1", name="ck_shop_profile_id_is_1"),
    )

    op.create_table(
        "admins",
        sa.Column("admin_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('admin','clerk')", name="ck_admins_role"),
    )

    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("open_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("nickname", sa.String(length=100), nullable=True),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("loyalty_points", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("preferences_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "categories",
        sa.Column("category_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "spec_groups",
        sa.Column("group_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=50), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "products",
        sa.Column("product_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.category_id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("inventory_status", sa.String(length=20), nullable=False, server_default=sa.text("'in_stock'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_products_status"),
        sa.CheckConstraint("inventory_status IN ('in_stock','sold_out')", name="ck_products_inventory_status"),
    )

    op.create_table(
        "spec_options",
        sa.Column("option_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("spec_groups.group_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("price_modifier", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("inventory_status", sa.String(length=20), nullable=False, server_default=sa.text("'in_stock'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("inventory_status IN ('in_stock','sold_out')", name="ck_spec_options_inventory_status"),
        sa.UniqueConstraint("group_id", "name", name="uq_spec_options_group_name"),
    )

    op.create_table(
        "product_categories",
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.category_id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "category_id"),
    )

    op.create_table(
        "product_spec_mappings",
        sa.Column("mapping_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("spec_groups.group_id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("product_id", "group_id", name="uq_product_spec_mappings_product_group"),
    )

    op.create_table(
        "orders",
        sa.Column("order_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_number", sa.String(length=50), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("guest_session_id", sa.String(length=64), nullable=True),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("address_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_scheduled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("total_price >= 0", name="ck_orders_total_price_non_negative"),
        sa.CheckConstraint(
            "status IN ('pending_payment','paid','in_production','ready_for_pickup','completed','cancelled','refund_pending','refunded')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint("order_type IN ('pickup','delivery')", name="ck_orders_order_type"),
    )

    op.create_table(
        "user_addresses",
        sa.Column("address_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_name", sa.String(length=50), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address_line", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(precision=53), nullable=True),
        sa.Column("lng", sa.Float(precision=53), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "order_items",
        sa.Column("item_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id"), nullable=True),
        sa.Column("product_name", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("selected_specs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
    )

    op.create_table(
        "payment_records",
        sa.Column("pay_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("record_type", sa.String(length=10), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("txn_id", sa.String(length=80), nullable=True, unique=True),
        sa.Column("out_trade_no", sa.String(length=50), nullable=True),
        sa.Column("matched_order_id", sa.BigInteger(), sa.ForeignKey("orders.order_id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_status", sa.String(length=20), nullable=False, server_default=sa.text("'unmatched'")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_notification_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount >= 0", name="ck_payment_records_amount_non_negative"),
        sa.CheckConstraint("record_type IN ('payment','refund')", name="ck_payment_records_record_type"),
        sa.CheckConstraint(
            "channel IN ('wechat_jsapi','wechat_native','static_qr','wechat_refund')",
            name="ck_payment_records_channel",
        ),
        sa.CheckConstraint(
            "match_status IN ('unmatched','auto_matched','manual_matched','failed')",
            name="ck_payment_records_match_status",
        ),
    )

    op.create_table(
        "loyalty_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.order_id"), nullable=True),
        sa.Column("delta_points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "reason IN ('order_paid','refund_rollback','coupon_grant','coupon_use')",
            name="ck_loyalty_transactions_reason",
        ),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("idempotency_key", sa.String(length=80), primary_key=True),
        sa.Column("scope", sa.String(length=50), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_type", sa.String(length=10), nullable=False),
        sa.Column("actor_admin_id", sa.BigInteger(), sa.ForeignKey("admins.admin_id"), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_table", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=50), nullable=True),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("curr_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("actor_type IN ('admin','user','system')", name="ck_audit_logs_actor_type"),
    )

    op.create_table(
        "coupons",
        sa.Column("coupon_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_in_order_id", sa.BigInteger(), sa.ForeignKey("orders.order_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("type IN ('free_any_drink')", name="ck_coupons_type"),
        sa.CheckConstraint("status IN ('active','used','expired','void')", name="ck_coupons_status"),
    )

    op.create_table(
        "print_jobs",
        sa.Column("job_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("try_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_try_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("printer_id", sa.String(length=50), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending','processing','done','failed')", name="ck_print_jobs_status"),
    )

    op.create_table(
        "want_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_categories_sort_order", "categories", ["sort_order"])
    op.create_index(
        "ix_orders_status_created",
        "orders",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_orders_user_created",
        "orders",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_orders_scheduled",
        "orders",
        ["is_scheduled", "scheduled_at"],
        postgresql_where=sa.text("is_scheduled = TRUE"),
    )
    op.create_index(
        "ix_payment_records_time_amount",
        "payment_records",
        [sa.text("paid_at DESC"), "amount"],
    )
    op.create_index(
        "ix_payment_records_type_channel",
        "payment_records",
        ["record_type", "channel"],
    )
    op.create_index(
        "ix_payment_records_order_match",
        "payment_records",
        ["matched_order_id"],
    )
    op.create_index("ix_coupons_user_status", "coupons", ["user_id", "status"])
    op.create_index(
        "ix_print_jobs_status_next",
        "print_jobs",
        ["status", sa.text("next_try_at ASC NULLS FIRST")],
    )
    op.create_index(
        "ix_want_events_product_time",
        "want_events",
        ["product_id", sa.text("created_at DESC")],
    )

    shop_settings_table = sa.table(
        "shop_settings",
        sa.column("key", sa.String(length=50)),
        sa.column("value", sa.Text()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        shop_settings_table,
        [
            {"key": "MULTI_CATEGORY_ENABLED", "value": "false", "description": "Enable multi-category mode"},
            {"key": "RESERVATION_ENABLED", "value": "false", "description": "Enable reservation flow"},
            {"key": "WANT_ENABLED", "value": "true", "description": "Enable want feature"},
            {"key": "SOLDOUT_STYLE", "value": "hide", "description": "Sold-out rendering style (hide|disabled)"},
            {"key": "RESERVATION_REMINDER_MINUTES", "value": "15", "description": "Reminder minutes for reservations"},
            {"key": "STATIC_MATCH_TIME_WINDOW_MIN", "value": "5", "description": "Static payment match window"},
            {"key": "DELIVERY_RADIUS_M", "value": "1500", "description": "Delivery radius meters"},
            {"key": "PRINT_RETRY_MAX", "value": "5", "description": "Max print retries"},
        ],
    )

    shop_profile_table = sa.table(
        "shop_profile",
        sa.column("id", sa.SmallInteger()),
        sa.column("is_open", sa.Boolean()),
        sa.column("open_hours_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("location_lat", sa.Float(precision=53)),
        sa.column("location_lng", sa.Float(precision=53)),
        sa.column("delivery_radius_m", sa.Integer()),
        sa.column("timezone", sa.String(length=64)),
    )
    op.bulk_insert(
        shop_profile_table,
        [
            {
                "id": 1,
                "is_open": True,
                "open_hours_json": [],
                "location_lat": None,
                "location_lng": None,
                "delivery_radius_m": 1500,
                "timezone": "Asia/Shanghai",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_want_events_product_time", table_name="want_events")
    op.drop_index("ix_print_jobs_status_next", table_name="print_jobs")
    op.drop_index("ix_coupons_user_status", table_name="coupons")
    op.drop_index("ix_payment_records_order_match", table_name="payment_records")
    op.drop_index("ix_payment_records_type_channel", table_name="payment_records")
    op.drop_index("ix_payment_records_time_amount", table_name="payment_records")
    op.drop_index("ix_orders_scheduled", table_name="orders")
    op.drop_index("ix_orders_user_created", table_name="orders")
    op.drop_index("ix_orders_status_created", table_name="orders")
    op.drop_index("ix_categories_sort_order", table_name="categories")

    op.drop_table("want_events")
    op.drop_table("print_jobs")
    op.drop_table("coupons")
    op.drop_table("audit_logs")
    op.drop_table("idempotency_keys")
    op.drop_table("loyalty_transactions")
    op.drop_table("payment_records")
    op.drop_table("order_items")
    op.drop_table("user_addresses")
    op.drop_table("orders")
    op.drop_table("product_spec_mappings")
    op.drop_table("product_categories")
    op.drop_table("spec_options")
    op.drop_table("products")
    op.drop_table("spec_groups")
    op.drop_table("categories")
    op.drop_table("users")
    op.drop_table("admins")
    op.drop_table("shop_profile")
    op.drop_table("shop_settings")
