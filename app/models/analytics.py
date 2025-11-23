"""用户行为分析埋点数据模型"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsEvent(Base):
    """
    用户行为埋点事件表

    设计要点:
    - event_id 作为主键实现天然幂等
    - 按 event_timestamp 分区便于归档历史数据
    - user_id/session_id 支持用户和匿名会话追踪
    - payload JSONB 灵活存储自定义属性
    """

    __tablename__ = "analytics_events"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, comment="事件唯一标识(UUID v4,前端生成)"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="用户ID(NULL表示匿名用户)"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, comment="会话标识(用户或匿名会话)"
    )
    event_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="事件类型: event/page/user"
    )
    event_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="事件名称: add_to_cart/page_view等"
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="前端事件发生时间戳(UTC)"
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="自定义事件属性(JSON格式)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="NOW()",
        nullable=False,
        comment="服务端接收时间(UTC)",
    )

    __table_args__ = (
        # 用户行为时序查询优化
        Index(
            "idx_analytics_user_event_time",
            "user_id",
            "event_timestamp",
            postgresql_ops={"event_timestamp": "DESC"},
        ),
        # 事件类型聚合查询优化
        Index(
            "idx_analytics_event_name_time",
            "event_name",
            "event_timestamp",
            postgresql_ops={"event_timestamp": "DESC"},
        ),
        # 按接收时间归档优化
        Index("idx_analytics_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
        # 会话分析优化
        Index(
            "idx_analytics_session_time",
            "session_id",
            "event_timestamp",
            postgresql_ops={"event_timestamp": "DESC"},
        ),
        {"comment": "用户行为埋点事件表"},
    )
