"""分布式锁工具,支持 Redis + PostgreSQL Advisory Lock 双重方案。"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from redis.asyncio import Redis, from_url
from redis.asyncio.lock import Lock as RedisLock
from redis.exceptions import RedisError
from structlog import get_logger

from app.core.settings import get_settings

logger = get_logger(__name__)


def _get_redis_client() -> Redis | None:
    """获取 Redis 客户端用于分布式锁。"""
    settings = get_settings()
    broker_url = settings.celery_broker_url
    if not broker_url or "redis://" not in broker_url:
        return None
    try:
        return from_url(broker_url, decode_responses=False, socket_connect_timeout=2)
    except RedisError:
        logger.warning("distributed_lock.redis_unavailable")
        return None


@asynccontextmanager
async def distributed_lock(
    lock_key: str,
    timeout: int = 10,
    blocking: bool = False,
    session: AsyncSession | None = None,
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
    redis_lock: RedisLock | None = None
    redis_acquired = False
    db_lock_conn: AsyncConnection | None = None
    db_lock_id: int | None = None

    try:
        redis_error = False
        if client is not None:
            try:
                redis_lock = client.lock(lock_key, timeout=timeout, blocking=blocking)
                redis_acquired = await redis_lock.acquire(blocking=blocking)
            except RedisError as exc:
                redis_error = True
                logger.error("distributed_lock.redis_error", lock_key=lock_key, error=str(exc))

        if redis_acquired:
            logger.debug("distributed_lock.acquired", lock_key=lock_key, backend="redis")
            yield True
            return

        if client is not None and not redis_error:
            # Redis 可用但锁被占用,直接返回失败,不再降级到 DB 以避免双写。
            logger.warning("distributed_lock.acquisition_failed", lock_key=lock_key)
            yield False
            return

        # Redis 不可用或异常,尝试 DB fallback
        db_acquired, db_lock_conn, db_lock_id = await _acquire_db_lock(
            session=session,
            lock_key=lock_key,
            blocking=blocking,
        )
        if db_acquired:
            logger.warning("distributed_lock.db_fallback_acquired", lock_key=lock_key)
            yield True
            return

        logger.warning("distributed_lock.fallback_unavailable", lock_key=lock_key)
        yield False

    finally:
        if redis_lock is not None and redis_acquired:
            try:
                await redis_lock.release()
                logger.debug("distributed_lock.released", lock_key=lock_key, backend="redis")
            except RedisError as exc:
                logger.warning("distributed_lock.release_failed", lock_key=lock_key, error=str(exc))

        if db_lock_conn is not None and db_lock_id is not None:
            await _release_db_lock(db_lock_conn, db_lock_id)


def _hash_lock_key(lock_key: str) -> int:
    digest = hashlib.sha1(lock_key.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    if value >= 2**63:
        value -= 2**64
    return value


async def _acquire_db_lock(
    *,
    session: AsyncSession | None,
    lock_key: str,
    blocking: bool,
) -> tuple[bool, AsyncConnection | None, int | None]:
    if session is None:
        return False, None, None
    bind = session.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False, None, None

    lock_id = _hash_lock_key(lock_key)
    function = "pg_advisory_lock" if blocking else "pg_try_advisory_lock"
    try:
        conn = await bind.connect()
    except Exception as exc:  # pragma: no cover - 连接失败仅记日志
        logger.error("distributed_lock.db_connect_failed", lock_key=lock_key, error=str(exc))
        return False, None, None

    try:
        result = await conn.execute(text(f"SELECT {function}(:lock_id)"), {"lock_id": lock_id})
        acquired = bool(result.scalar_one_or_none())
        if not acquired:
            await conn.close()
            return False, None, None
    except Exception as exc:  # pragma: no cover - SQL 执行异常仅记日志
        logger.error("distributed_lock.db_fallback_error", lock_key=lock_key, error=str(exc))
        await conn.close()
        return False, None, None

    return True, conn, lock_id


async def _release_db_lock(conn: AsyncConnection, lock_id: int) -> None:
    try:
        await conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    except Exception as exc:  # pragma: no cover - 仅记日志
        logger.warning("distributed_lock.db_unlock_failed", lock_id=lock_id, error=str(exc))
    finally:
        await conn.close()
