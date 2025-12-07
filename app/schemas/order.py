from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class OrderItemSelectedSpecSchema(BaseModel):
    spec_id: int | None = None
    option_id: int = Field(..., gt=0)
    option_name: str | None = None
    price_modifier: float | None = None


class OrderItemCreateSchema(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=50)
    selected_specs: list[OrderItemSelectedSpecSchema] = Field(default_factory=list, max_length=10)
    spec_option_ids: list[int] = Field(
        default_factory=list,
        max_length=10,
        validation_alias=AliasChoices("spec_option_ids"),
    )

    @model_validator(mode="after")
    def _merge_selected_spec_ids(self) -> OrderItemCreateSchema:
        option_ids = list(self.spec_option_ids)
        if not option_ids and self.selected_specs:
            option_ids = [spec.option_id for spec in self.selected_specs if spec.option_id]
        # 去重保持顺序
        deduped: list[int] = []
        for option_id in option_ids:
            if option_id not in deduped:
                deduped.append(option_id)
        self.spec_option_ids = deduped
        return self


class OrderAddressSchema(BaseModel):
    """配送/取餐地址信息。"""

    address: str | None = None
    detail: str | None = None
    name: str | None = None
    phone: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    model_config = ConfigDict(extra="ignore")


class OrderDeliveryAddressSchema(OrderAddressSchema):
    """兼容历史命名的别名。"""


class OrderBaseRequestSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    shop_id: int = Field(..., ge=1)
    items: list[OrderItemCreateSchema] = Field(..., min_length=1, max_length=30)
    order_type: Literal["pickup", "delivery"] = Field(
        default="pickup",
        validation_alias=AliasChoices("delivery_type", "order_type"),
        serialization_alias="delivery_type",
    )
    dining_type: Literal["dine-in", "takeout"] | None = None
    scheduled_at: datetime | None = Field(default=None)
    address: OrderAddressSchema | None = None
    user_phone: str | None = Field(default=None, min_length=5, max_length=30)
    coupon_id: int | None = Field(default=None, description="使用的优惠券 ID")
    use_points: bool = Field(default=False, description="是否自动使用可用积分")
    points_use: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("points_use"),
        description="兼容旧字段，若 use_points=true 且未显式指定则自动最大化使用",
    )
    notes: str | None = Field(default=None, max_length=200)
    guest_session_id: str | None = Field(default=None, max_length=80)

    @property
    def delivery_type(self) -> str:
        return self.order_type

    @field_validator("user_phone")
    @classmethod
    def _strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("scheduled_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("scheduled_at 必须包含时区信息。")
        return value

    @model_validator(mode="after")
    def _sync_points_use(self) -> OrderBaseRequestSchema:
        if self.use_points and self.points_use == 0:
            # 使用一个足够大的值，实际扣减时会受可用积分/封顶限制
            self.points_use = 1_000_000_000
        return self


class OrderCalculateRequestSchema(OrderBaseRequestSchema):
    """价格试算请求"""


class OrderCreateRequestSchema(OrderBaseRequestSchema):
    user_phone: str = Field(..., min_length=5, max_length=30)


class OrderItemSchema(BaseModel):
    item_id: int
    product_id: int | None
    product_name: str
    quantity: int
    unit_price: float
    selected_specs: list[dict[str, Any]]


class PriceBreakdownItemSchema(BaseModel):
    """单品价格明细"""

    product_id: int
    product_name: str
    quantity: int
    base_price: float
    specs: list[dict[str, Any]]
    unit_price: float
    subtotal: float


class CouponApplicabilitySchema(BaseModel):
    """优惠券使用信息"""

    coupon_id: int
    type: str
    discount_amount: float
    min_order_amount: float | None = None
    is_applicable: bool
    reason: str = ""


class PointsInfoSchema(BaseModel):
    """积分抵扣信息"""

    available: int
    used: int
    discount: float
    exchange_rate: int = 100


class OrderCalculateResponseSchema(BaseModel):
    """价格试算响应"""

    subtotal: float
    coupon_discount: float = 0.0
    points_discount: float = 0.0
    delivery_fee: float = 0.0
    final_amount: float
    breakdown: list[PriceBreakdownItemSchema] = Field(default_factory=list)
    coupon_info: CouponApplicabilitySchema | None = None
    points_info: PointsInfoSchema | None = None
    eta_minutes: int | None = Field(default=None, description="预计等待/送达分钟数")
    eta_text: str | None = Field(default=None, description="预计时间文案")


class OrderResponseSchema(BaseModel):
    order_id: int
    order_number: str
    status: str
    order_type: str
    total_price: float
    created_at: datetime
    is_scheduled: bool
    scheduled_at: datetime | None
    reminder_sent_at: datetime | None
    eta_minutes: int | None = Field(default=None, description="预计等待/送达分钟数")
    eta_text: str | None = Field(default=None, description="预计时间文案")
    pickup_code: str | None = Field(default=None, description="取餐码（支付成功后生成）")
    items: list[OrderItemSchema]


class OrderPaymentJsapiRequestSchema(BaseModel):
    payer_open_id: str = Field(..., min_length=1, max_length=128)
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OrderPaymentNativeRequestSchema(BaseModel):
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OrderPaymentInitiateResponseSchema(BaseModel):
    order_id: int
    channel: str
    payload: dict[str, Any]


class AdminOrderCreateRequestSchema(BaseModel):
    items: list[OrderItemCreateSchema] = Field(..., min_length=1, max_length=50)
    payment_channel: Literal["wechat_jsapi", "wechat_native", "static_qr", "cash", "pos_card"]
    order_type: Literal["pickup"] = Field(default="pickup")
    notes: str | None = Field(default=None, max_length=500)
    print_job: bool = Field(default=True)
    buyer_open_id: str | None = Field(default=None, max_length=255)
    buyer_phone: str | None = Field(default=None, max_length=30)
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("buyer_open_id", "guest_session_id", "buyer_phone", mode="before")
    @classmethod
    def _clean_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AdminOrderResponseSchema(BaseModel):
    order_id: int
    order_number: str
    status: str
    payment_status: str
    payment_channel: str
    total_price: float
    created_at: datetime
    print_job_id: int | None = None


class OpsAutoCancelRequestSchema(BaseModel):
    cutoff_minutes: int = Field(default=30, ge=1, le=1440)
    limit: int = Field(default=100, ge=1, le=500)
    reason: str | None = Field(default=None, max_length=120)


class OpsAutoCancelResponseSchema(BaseModel):
    cancelled_order_ids: list[int]
    count: int
    cutoff_iso: datetime
    source: Literal["http", "celery", "cron"]
    operator_admin_id: int


# ============ Admin 订单管理 Schema ============


class AdminOrderListQuerySchema(BaseModel):
    """订单列表查询参数"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: list[str] | None = Field(default=None, description="订单状态筛选（多选）")
    payment_status: list[str] | None = Field(default=None, description="支付状态筛选（多选）")
    order_type: str | None = Field(default=None, description="订单类型筛选")
    payment_channel: str | None = Field(default=None, description="支付渠道筛选")
    start_time: datetime | None = Field(default=None, description="开始时间")
    end_time: datetime | None = Field(default=None, description="结束时间")
    user_phone: str | None = Field(default=None, max_length=30, description="用户手机号")
    order_number: str | None = Field(default=None, max_length=50, description="订单号")
    pickup_code: str | None = Field(default=None, max_length=20, description="取餐码")


class AdminOrderItemSchema(BaseModel):
    """订单商品项（管理端）"""

    item_id: int
    product_id: int | None
    product_name: str
    quantity: int
    unit_price: float
    selected_specs: list[dict[str, Any]]
    subtotal: float


class AdminOrderDetailSchema(BaseModel):
    """订单详情（管理端）"""

    order_id: int
    order_number: str
    status: str
    payment_status: str
    payment_channel: str | None
    order_type: str
    source: str | None
    total_price: float
    coupon_discount: float
    points_discount: float
    final_amount: float
    user_id: int | None
    user_phone: str | None
    user_nickname: str | None
    pickup_code: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_by_admin_id: int | None
    items: list[AdminOrderItemSchema]
    address: OrderAddressSchema | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list, description="状态流转时间线")


class AdminOrderListItemSchema(BaseModel):
    """订单列表项（管理端）"""

    order_id: int
    order_number: str
    status: str
    payment_status: str
    payment_channel: str | None
    order_type: str
    total_price: float
    user_phone: str | None
    pickup_code: str | None
    created_at: datetime
    paid_at: datetime | None


class AdminOrderListResponseSchema(BaseModel):
    """订单列表响应"""

    items: list[AdminOrderListItemSchema]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminOrderStatusUpdateRequestSchema(BaseModel):
    """订单状态修改请求"""

    status: Literal["in_production", "ready_for_pickup", "completed", "cancelled"]
    reason: str | None = Field(
        default=None, max_length=200, description="状态变更原因（取消时必填）"
    )

    @model_validator(mode="after")
    def _validate_reason(self) -> AdminOrderStatusUpdateRequestSchema:
        if self.status == "cancelled" and not self.reason:
            raise ValueError("取消订单时必须填写原因")
        return self


class AdminOrderRefundRequestSchema(BaseModel):
    """订单退款请求"""

    refund_type: Literal["online", "offline"] = Field(default="online")
    amount: float = Field(..., gt=0, description="退款金额")
    reason: str = Field(..., min_length=1, max_length=200, description="退款原因（必填）")


class AdminOrderRefundResponseSchema(BaseModel):
    """订单退款响应"""

    order_id: int
    refund_type: str
    amount: float
    status: str
    refund_id: str | None = None
    message: str


class AdminPickupCodeUpdateRequestSchema(BaseModel):
    """取餐码修改请求"""

    new_pickup_code: str | None = Field(
        default=None, min_length=4, max_length=20, description="新取餐码（为空则自动生成）"
    )
    reason: str = Field(..., min_length=1, max_length=200, description="修改原因（必填）")


class AdminPickupCodeUpdateResponseSchema(BaseModel):
    """取餐码修改响应"""

    order_id: int
    old_pickup_code: str | None
    new_pickup_code: str
    updated_at: datetime
