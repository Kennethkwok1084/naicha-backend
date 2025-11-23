"""用户行为分析埋点数据Schema"""

import json
from typing import Any, Literal

from pydantic import UUID4, BaseModel, Field, field_validator


class AnalyticsEventSchema(BaseModel):
    """单个埋点事件Schema"""

    id: UUID4 = Field(
        ..., description="事件唯一标识(UUID v4)", examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    type: Literal["event", "page", "user"] = Field(
        ..., description="事件类型: event(操作)/page(页面)/user(用户属性)"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="事件名称",
        examples=["add_to_cart", "page_view", "pay_success"],
    )
    timestamp: int = Field(..., gt=0, description="Unix毫秒时间戳", examples=[1700000000000])
    payload: dict[str, Any] | None = Field(
        default=None,
        description="自定义事件属性(最多30个字段,总大小≤8KB,嵌套≤4层)",
        examples=[{"productId": 123, "quantity": 2, "price": 15.0}],
    )

    @field_validator("name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        """
        事件名校验: 允许字母、数字、下划线、连字符
        兼容 snake_case 和 camelCase 命名风格
        """
        # 移除合法字符后检查是否有剩余
        sanitized = v.replace("_", "").replace("-", "")
        if not sanitized.isalnum():
            raise ValueError("事件名只能包含字母、数字、下划线和连字符")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict | None) -> dict | None:
        """
        payload 校验:
        1. 限制字段数量 ≤ 30
        2. 限制总大小 ≤ 8KB (序列化后)
        3. 限制嵌套深度 ≤ 4层
        """
        if v is None:
            return v

        # 1. 字段数量限制
        if len(v) > 30:
            raise ValueError("payload 字段数量不能超过30个")

        # 2. 总大小限制 (序列化后)
        try:
            payload_json = json.dumps(v, ensure_ascii=False)
            payload_bytes = len(payload_json.encode("utf-8"))
            if payload_bytes > 8192:  # 8KB
                raise ValueError(f"payload 总大小({payload_bytes}字节)超过限制(8KB)")
        except (TypeError, ValueError) as e:
            raise ValueError(f"payload 序列化失败: {e!s}")

        # 3. 嵌套深度限制
        def check_depth(obj: Any, current: int = 0, max_depth: int = 4) -> None:
            if current > max_depth:
                raise ValueError(f"payload 嵌套层级不能超过{max_depth}层")

            if isinstance(obj, dict):
                for val in obj.values():
                    check_depth(val, current + 1, max_depth)
            elif isinstance(obj, list):
                for item in obj:
                    check_depth(item, current + 1, max_depth)

        check_depth(v)
        return v


class BatchEventsRequest(BaseModel):
    """批量上报埋点事件请求"""

    events: list[AnalyticsEventSchema] = Field(
        ..., min_length=1, max_length=10, description="事件列表(单次最多10条)"
    )

    @field_validator("events")
    @classmethod
    def validate_unique_ids(cls, v: list[AnalyticsEventSchema]) -> list[AnalyticsEventSchema]:
        """确保批次内事件ID唯一"""
        event_ids = [e.id for e in v]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("批次内存在重复的事件ID")
        return v


class BatchEventsResponse(BaseModel):
    """批量上报响应(实际返回204,此Schema用于文档)"""

    message: str = Field(default="Events queued successfully", description="处理状态")
    queued_count: int = Field(..., description="已加入队列的事件数量")
