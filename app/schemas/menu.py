from __future__ import annotations

from pydantic import BaseModel


class MenuSpecOptionSchema(BaseModel):
    option_id: int
    name: str
    price_modifier: float
    inventory_status: str
    sort_order: int


class MenuSpecGroupSchema(BaseModel):
    group_id: int
    name: str
    sort_order: int
    options: list[MenuSpecOptionSchema]


class MenuProductSchema(BaseModel):
    product_id: int
    name: str
    description: str | None
    image_url: str | None
    base_price: float
    status: str
    inventory_status: str
    spec_groups: list[MenuSpecGroupSchema]


class MenuCategorySchema(BaseModel):
    category_id: int
    name: str
    sort_order: int
    products: list[MenuProductSchema]


class MenuResponseSchema(BaseModel):
    categories: list[MenuCategorySchema]
    uncategorized_products: list[MenuProductSchema]
    multi_category_enabled: bool
