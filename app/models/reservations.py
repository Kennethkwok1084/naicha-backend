from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BIGINT_PK, Base, TimestampMixin


class ReservationSlot(Base, TimestampMixin):
    __tablename__ = "reservation_slots"

    slot_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_reservation_slots_capacity_positive"),
        CheckConstraint(
            "reserved_count >= 0",
            name="ck_reservation_slots_reserved_count_non_negative",
        ),
        UniqueConstraint("slot_start", name="uq_reservation_slots_start"),
    )
