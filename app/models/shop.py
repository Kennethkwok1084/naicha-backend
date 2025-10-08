from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ShopSetting(Base):
    __tablename__ = "shop_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShopProfile(Base, TimestampMixin):
    __tablename__ = "shop_profile"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    is_open: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    open_hours_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    delivery_radius_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64), server_default=text("'Asia/Shanghai'"), nullable=False
    )

    __table_args__ = (CheckConstraint("id = 1", name="ck_shop_profile_id_is_1"),)
