from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BIGINT_PK, Base, TimestampMixin


class MaintenanceJob(Base, TimestampMixin):
    __tablename__ = "maintenance_jobs"

    job_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_maintenance_jobs_status",
        ),
        Index("ix_maintenance_jobs_status_schedule", "status", "scheduled_at"),
        Index("ix_maintenance_jobs_type_schedule", "job_type", "scheduled_at"),
    )


class MaintenanceHeartbeat(Base):
    __tablename__ = "maintenance_heartbeats"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
