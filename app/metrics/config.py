from __future__ import annotations

from prometheus_client import Counter

CONFIG_REQUEST_TOTAL = Counter(
    "config_request_total",
    "前端配置接口请求计数",
    ["result"],  # hit_304, miss, error
)

CONFIG_CACHE_HIT_TOTAL = Counter(
    "config_cache_hit_total",
    "配置缓存命中次数",
    ["cache_layer"],  # redis, json_fallback
)

__all__ = ["CONFIG_CACHE_HIT_TOTAL", "CONFIG_REQUEST_TOTAL"]
