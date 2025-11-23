"""用户行为分析埋点API路由"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from starlette.responses import JSONResponse

from app.api.dependencies.auth import get_current_user_optional
from app.core.rate_limiter import limiter
from app.metrics.analytics import ANALYTICS_EVENTS_RECEIVED_TOTAL
from app.models.accounts import User
from app.schemas.analytics import BatchEventsRequest
from app.workers.tasks import batch_ingest_analytics_events

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.post(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="批量上报用户行为埋点",
    description="""
    批量上报用户行为埋点事件,用于分析用户行为、页面访问、业务转化漏斗等。
    
    **限制**:
    - 单次最多10条事件
    - 每条事件 payload 不超过 8KB
    - 匿名用户必须提供 X-Session-Id 请求头
    - 限流: 100次/分钟/IP
    
    **幂等性**:
    基于 event.id (UUID) 主键去重,重复事件会被自动忽略
    
    **异步处理**:
    事件会立即加入Celery队列,由Worker异步批量入库,API立即返回204
    """,
)
@limiter.limit("100/minute")
async def batch_report_events(
    request: Request,
    body: BatchEventsRequest,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    批量上报用户行为埋点

    前端触发时机:
    - 每隔15秒自动上报
    - 累积10条事件时立即上报
    - 页面关闭前上报剩余事件

    事件类型:
    - event: 用户操作(加购/下单/支付/取消)
    - page: 页面访问(进入/离开/停留时长)
    - user: 用户属性变更(登录/登出)
    """
    # 1. 提取用户身份信息
    user_id = current_user.user_id if current_user else None
    session_id = request.headers.get("X-Session-Id")

    # 2. 匿名用户必须提供会话ID
    if not user_id and not session_id:
        raise HTTPException(
            status_code=400,
            detail="匿名用户必须提供 X-Session-Id 请求头",
        )

    # 3. 构建事件数据(整批打包投递,减少broker往返)
    events_data = []
    for event in body.events:
        events_data.append(
            {
                "event_id": str(event.id),
                "user_id": user_id,
                "session_id": session_id or f"user_{user_id}",
                "event_type": event.type,
                "event_name": event.name,
                "event_timestamp_ms": event.timestamp,
                "payload": event.payload,
            }
        )

    # 4. 异步投递到Celery队列(不等待执行结果)
    batch_ingest_analytics_events.apply_async(
        kwargs={"events_data": events_data},
        queue="analytics",  # 独立队列,避免影响核心业务
        priority=1,  # 低优先级
        expires=300,  # 5分钟过期,避免积压过期数据
    )

    # 5. 按事件类型统计接收指标
    for event in body.events:
        ANALYTICS_EVENTS_RECEIVED_TOTAL.labels(event_type=event.type).inc()

    logger.info(
        "analytics.events_queued",
        user_id=user_id,
        session_id=session_id,
        event_count=len(body.events),
    )

    # 6. 立即返回204(事件已加入队列)
    return Response(status_code=204)


@router.get(
    "/health",
    summary="埋点系统健康检查",
    description="检查Celery队列积压情况,超过10000条事件告警",
)
async def analytics_health():
    """
    埋点系统健康检查

    监控指标:
    - analytics队列长度（从Redis broker获取真实队列积压）
    - 是否存在大量积压

    状态码:
    - 200: 健康
    - 503: 队列积压严重或检查失败
    """
    try:
        import redis

        from app.core.settings import get_settings

        settings = get_settings()

        # 从Redis broker获取真实队列长度
        queue_size = 0
        if "redis" in settings.celery_broker_url.lower():
            try:
                redis_client = redis.from_url(settings.celery_broker_url, decode_responses=False)
                # Celery在Redis中的队列键格式: celery (默认队列) 或 analytics
                queue_size = redis_client.llen("analytics") or 0
                redis_client.close()
            except Exception as redis_exc:
                logger.warning("analytics.redis_check_failed", error=str(redis_exc))
                # Redis连接失败，降级为0（避免阻塞健康检查）
                queue_size = 0

        # 队列积压超过阈值告警
        if queue_size > 10000:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "reason": "analytics queue backlog",
                    "queue_size": queue_size,
                    "threshold": 10000,
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "queue_size": queue_size,
            },
        )

    except Exception as exc:
        logger.error("analytics.health_check_failed", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "reason": str(exc),
            },
        )
