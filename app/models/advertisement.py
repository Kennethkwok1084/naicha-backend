from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_PK, Base, CreatedAtMixin, TimestampMixin


class AdSlot(Base, CreatedAtMixin):
    __tablename__ = "ad_slots"

    slot_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    placements: Mapped[list[AdPlacement]] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AdCreative(Base, TimestampMixin):
    __tablename__ = "ad_creatives"

    creative_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    jump_type: Mapped[str] = mapped_column(String(20), nullable=False)
    jump_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
        default=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )
    platforms: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    placements: Mapped[list[AdPlacement]] = relationship(
        back_populates="creative",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "jump_type IN ('miniapp_page','h5','none')",
            name="ck_ad_creatives_jump_type",
        ),
        Index("ix_ad_creatives_enabled_priority", "enabled", "priority"),
    )


class AdPlacement(Base, TimestampMixin):
    __tablename__ = "ad_placements"

    placement_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    slot_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("ad_slots.code", ondelete="CASCADE"),
        nullable=False,
    )
    creative_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ad_creatives.creative_id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    slot: Mapped[AdSlot] = relationship(back_populates="placements")
    creative: Mapped[AdCreative] = relationship(back_populates="placements")

    __table_args__ = (
        UniqueConstraint("slot_code", "creative_id", name="uq_ad_placements_slot_creative"),
        Index("ix_ad_placements_slot_code", "slot_code"),
    )
