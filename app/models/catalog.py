from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin


class Category(Base, CreatedAtMixin):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.category_id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)
    inventory_status: Mapped[str] = mapped_column(
        String(20), server_default="in_stock", nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_products_status",
        ),
        CheckConstraint(
            "inventory_status IN ('in_stock','sold_out')",
            name="ck_products_inventory_status",
        ),
    )

    categories: Mapped[list[Category]] = relationship(
        secondary="product_categories",
        backref="products",
        lazy="selectin",
    )


class ProductCategory(Base):
    __tablename__ = "product_categories"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.category_id", ondelete="CASCADE"),
        primary_key=True,
    )


class SpecGroup(Base, CreatedAtMixin):
    __tablename__ = "spec_groups"

    group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)


class SpecOption(Base, CreatedAtMixin):
    __tablename__ = "spec_options"

    option_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("spec_groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    price_modifier: Mapped[float] = mapped_column(
        Numeric(10, 2), server_default="0.00", nullable=False
    )
    inventory_status: Mapped[str] = mapped_column(
        String(20), server_default="in_stock", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "inventory_status IN ('in_stock','sold_out')",
            name="ck_spec_options_inventory_status",
        ),
        UniqueConstraint("group_id", "name", name="uq_spec_options_group_name"),
    )


class ProductSpecMapping(Base):
    __tablename__ = "product_spec_mappings"

    mapping_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("spec_groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("product_id", "group_id", name="uq_product_spec_mappings_product_group"),
    )


Index("ix_categories_sort_order", Category.sort_order)
