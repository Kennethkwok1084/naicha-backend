"""add maintenance job tables

Revision ID: 20251028_add_maintenance_jobs
Revises: 20251024_add_product_stock_quantity
Create Date: 2025-10-28 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251028_add_maintenance_jobs"
down_revision = "20251024_add_product_stock_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_jobs",
        sa.Column("job_id", sa.BigInteger(), primary_key=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_maintenance_jobs_status",
        ),
    )
    op.create_index(
        "ix_maintenance_jobs_status_schedule",
        "maintenance_jobs",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_maintenance_jobs_type_schedule",
        "maintenance_jobs",
        ["job_type", "scheduled_at"],
    )

    op.create_table(
        "maintenance_heartbeats",
        sa.Column("name", sa.String(length=50), primary_key=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("maintenance_heartbeats")
    op.drop_index("ix_maintenance_jobs_type_schedule", table_name="maintenance_jobs")
    op.drop_index("ix_maintenance_jobs_status_schedule", table_name="maintenance_jobs")
    op.drop_table("maintenance_jobs")
