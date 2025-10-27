"""数据库查询性能分析工具"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog import get_logger

logger = get_logger(__name__)

# 慢查询阈值(毫秒)
SLOW_QUERY_THRESHOLD_MS = 100


class QueryProfiler:
    """SQL查询性能分析器"""

    def __init__(self, threshold_ms: int = SLOW_QUERY_THRESHOLD_MS):
        self.threshold_ms = threshold_ms
        self.query_stats: dict[str, dict[str, Any]] = {}

    def log_slow_query(
        self,
        statement: str,
        parameters: Any,
        duration_ms: float,
        context: str = "",
    ) -> None:
        """记录慢查询"""
        if duration_ms > self.threshold_ms:
            logger.warning(
                "slow_query_detected",
                duration_ms=duration_ms,
                threshold_ms=self.threshold_ms,
                statement=statement[:200],  # 截断长SQL
                parameters=str(parameters)[:100],
                context=context,
            )


# 全局分析器实例
profiler = QueryProfiler()


def setup_query_profiling(engine: AsyncEngine | Engine) -> None:
    """为引擎设置查询性能分析"""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """查询开始前记录时间"""
        conn.info.setdefault("query_start_time", []).append(time.time())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """查询结束后计算耗时"""
        query_start_times = conn.info.get("query_start_time", [])
        if query_start_times:
            start_time = query_start_times.pop()
            duration_ms = (time.time() - start_time) * 1000
            profiler.log_slow_query(statement, parameters, duration_ms)

    logger.info(
        "query_profiling_enabled",
        threshold_ms=profiler.threshold_ms,
        engine=str(engine),
    )
