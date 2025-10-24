"""分布式锁工具,基于 Redis 实现并发控制。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.exceptions import RedisError
from structlog import get_logger

from app.core.settings import get_settings

logger = get_logger(__name__)


def _get_redis_client() -> redis.Redis | None:
    """获取 Redis 客户端用于分布式锁。"""
    settings = get_settings()
    broker_url = settings.celery_broker_url
    if not broker_url or "redis://" not in broker_url:
        return None
    try:
        return redis.from_url(broker_url, decode_responses=False, socket_connect_timeout=2)
    except RedisError:
        logger.warning("distributed_lock.redis_unavailable")
        return None


@asynccontextmanager
async def distributed_lock(
    lock_key: str,
    timeout: int = 10,
    blocking: bool = False,
) -> AsyncIterator[bool]:
    """分布式锁上下文管理器。

    Args:
        lock_key: 锁的唯一标识符 (建议格式: "service:resource_type:resource_id")
        timeout: 锁的超时时间 (秒),防止死锁
        blocking: 是否阻塞等待锁释放

    Yields:
        bool: 是否成功获取锁 (True=已获取, False=获取失败但降级继续)

    Example:
        async with distributed_lock("payment_match:txn:123", timeout=5) as acquired:
            if not acquired:
                logger.warning("lock_acquisition_failed")
                # 降级处理或抛出异常
            # 执行需要互斥的业务逻辑
    """
    client = _get_redis_client()
    lock: redis.lock.Lock | None = None
    acquired = False

    if client is None:
        logger.warning("distributed_lock.client_unavailable", lock_key=lock_key)
        yield False  # 降级: Redis 不可用时允许继续执行 (调用方需自行决定是否抛异常)
        return

    try:
        lock = client.lock(lock_key, timeout=timeout, blocking=blocking)
        acquired = await lock.acquire(blocking=blocking)

        if not acquired:
            logger.warning("distributed_lock.acquisition_failed", lock_key=lock_key)
            yield False
        else:
            logger.debug("distributed_lock.acquired", lock_key=lock_key)
            yield True

    except RedisError as exc:
        logger.error("distributed_lock.error", lock_key=lock_key, error=str(exc))
        yield False  # 降级: 锁操作异常时允许继续执行

    finally:
        if lock is not None and acquired:
            try:
                await lock.release()
                logger.debug("distributed_lock.released", lock_key=lock_key)
            except RedisError as exc:
                logger.warning("distributed_lock.release_failed", lock_key=lock_key, error=str(exc))
