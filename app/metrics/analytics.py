"""用户行为分析埋点相关Prometheus指标"""

from prometheus_client import Counter, Histogram

# API层指标 - 按事件类型打标签便于对齐计算
ANALYTICS_EVENTS_RECEIVED_TOTAL = Counter(
    "analytics_events_received_total", "API接收到的埋点事件总数(按事件类型)", ["event_type"]
)

# Worker层指标 - 入库成功
ANALYTICS_EVENTS_INSERTED_TOTAL = Counter(
    "analytics_events_inserted_total", "成功插入数据库的事件数(按事件类型)", ["event_type"]
)

# Worker层指标 - 重复事件
ANALYTICS_EVENTS_DUPLICATES_TOTAL = Counter(
    "analytics_events_duplicates_total",
    "重复事件数(主键冲突被忽略)",
)

# Worker层指标 - 入库失败
ANALYTICS_EVENTS_FAILED_TOTAL = Counter(
    "analytics_events_failed_total",
    "入库失败次数(重试耗尽后)",
)

# Worker层指标 - 批量入库延迟
ANALYTICS_BATCH_INSERT_DURATION_SECONDS = Histogram(
    "analytics_batch_insert_duration_seconds",
    "批量插入事件的耗时(秒)",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Worker层指标 - 批量大小分布
ANALYTICS_BATCH_SIZE = Histogram(
    "analytics_batch_size", "每批次插入的事件数量", buckets=[1, 5, 10, 20, 50, 100, 200, 500]
)
