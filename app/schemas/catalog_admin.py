"""商品管理后台 Schema 定义"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ============ 分类 (Category) ============
class CategoryCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)


class CategoryUpdateSchema(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    sort_order: int | None = Field(None, ge=0)


class CategoryResponseSchema(BaseModel):
    category_id: int
    name: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoriesListResponseSchema(BaseModel):
    total: int
    items: list[CategoryResponseSchema]


# ============ 商品 (Product) ============
class ProductCreateSchema(BaseModel):
    category_id: int | None = None
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    image_url: str | None = Field(None, max_length=255)
    base_price: float = Field(..., gt=0, le=9999.99)
    status: str = Field(default="active")
    inventory_status: str = Field(default="in_stock")
    stock_quantity: int = Field(default=0, ge=0)
    category_ids: list[int] | None = Field(default=None, description="关联的分类 ID 列表")
    spec_group_ids: list[int] | None = Field(default=None, description="关联的规格组 ID 列表")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("active", "inactive"):
            raise ValueError("status 必须是 active 或 inactive")
        return v

    @field_validator("inventory_status")
    @classmethod
    def validate_inventory_status(cls, v: str) -> str:
        if v not in ("in_stock", "sold_out"):
            raise ValueError("inventory_status 必须是 in_stock 或 sold_out")
        return v


class ProductUpdateSchema(BaseModel):
    category_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    image_url: str | None = Field(None, max_length=255)
    base_price: float | None = Field(None, gt=0, le=9999.99)
    status: str | None = None
    inventory_status: str | None = None
    stock_quantity: int | None = Field(None, ge=0)
    category_ids: list[int] | None = None
    spec_group_ids: list[int] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "inactive"):
            raise ValueError("status 必须是 active 或 inactive")
        return v

    @field_validator("inventory_status")
    @classmethod
    def validate_inventory_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("in_stock", "sold_out"):
            raise ValueError("inventory_status 必须是 in_stock 或 sold_out")
        return v


class ProductResponseSchema(BaseModel):
    product_id: int
    category_id: int | None
    name: str
    description: str | None
    image_url: str | None
    base_price: float
    status: str
    inventory_status: str
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
    category_ids: list[int] = Field(default_factory=list)
    spec_group_ids: list[int] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProductsListResponseSchema(BaseModel):
    total: int
    items: list[ProductResponseSchema]


class ProductBatchStatusUpdateSchema(BaseModel):
    product_ids: list[int] = Field(..., min_length=1)
    status: str | None = None
    inventory_status: str | None = None
    reason: str = Field(..., min_length=1, max_length=200, description="批量操作原因（必填）")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "inactive"):
            raise ValueError("status 必须是 active 或 inactive")
        return v

    @field_validator("inventory_status")
    @classmethod
    def validate_inventory_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("in_stock", "sold_out"):
            raise ValueError("inventory_status 必须是 in_stock 或 sold_out")
        return v


# ============ 规格组 (SpecGroup) ============
class SpecGroupCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0)


class SpecGroupUpdateSchema(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    sort_order: int | None = Field(None, ge=0)


class SpecGroupResponseSchema(BaseModel):
    group_id: int
    name: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SpecGroupsListResponseSchema(BaseModel):
    total: int
    items: list[SpecGroupResponseSchema]


# ============ 规格选项 (SpecOption) ============
class SpecOptionCreateSchema(BaseModel):
    group_id: int
    name: str = Field(..., min_length=1, max_length=50)
    price_modifier: float = Field(default=0.0, ge=-999.99, le=999.99)
    inventory_status: str = Field(default="in_stock")
    sort_order: int = Field(default=0, ge=0)

    @field_validator("inventory_status")
    @classmethod
    def validate_inventory_status(cls, v: str) -> str:
        if v not in ("in_stock", "sold_out"):
            raise ValueError("inventory_status 必须是 in_stock 或 sold_out")
        return v


class SpecOptionUpdateSchema(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    price_modifier: float | None = Field(None, ge=-999.99, le=999.99)
    inventory_status: str | None = None
    sort_order: int | None = Field(None, ge=0)

    @field_validator("inventory_status")
    @classmethod
    def validate_inventory_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("in_stock", "sold_out"):
            raise ValueError("inventory_status 必须是 in_stock 或 sold_out")
        return v


class SpecOptionResponseSchema(BaseModel):
    option_id: int
    group_id: int
    name: str
    price_modifier: float
    inventory_status: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SpecOptionsListResponseSchema(BaseModel):
    total: int
    items: list[SpecOptionResponseSchema]


# ============ 删除操作 ============
class DeleteWithReasonSchema(BaseModel):
    reason: str = Field(..., min_length=1, max_length=200, description="删除原因（必填）")


# ============ 批量导入 ============
class ProductImportRowSchema(BaseModel):
    """单行导入数据"""

    row_number: int
    category_name: str | None
    product_name: str
    description: str | None
    base_price: float
    status: str = "active"
    inventory_status: str = "in_stock"
    stock_quantity: int = 0
    spec_groups: str | None = None  # 逗号分隔的规格组名


class ProductImportResultSchema(BaseModel):
    """导入结果"""

    success_count: int
    error_count: int
    errors: list[dict] = Field(default_factory=list)  # {row_number, error_message}


class ProductImportResponseSchema(BaseModel):
    """批量导入响应"""

    task_id: str | None = None  # 异步任务 ID（未来扩展）
    result: ProductImportResultSchema
