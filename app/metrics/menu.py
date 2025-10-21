from __future__ import annotations

from threading import Lock

from prometheus_client import Counter, Gauge

MENU_CACHE_LOOKUP_TOTAL = Counter(
    "menu_cache_lookup_total",
    "菜单缓存查询次数按结果分类。",
    ["result"],
)
MENU_CACHE_HIT_RATE = Gauge(
    "menu_cache_hit_rate",
    "菜单缓存命中率(0-1)。",
)

_lock = Lock()
_hits = 0
_total = 0


def _record(result: str) -> None:
    global _hits, _total
    with _lock:
        _total += 1
        MENU_CACHE_LOOKUP_TOTAL.labels(result=result).inc()
        if result == "hit":
            _hits += 1
        MENU_CACHE_HIT_RATE.set(_hits / _total if _total else 0.0)


def record_cache_hit() -> None:
    _record("hit")


def record_cache_miss() -> None:
    _record("miss")


__all__ = [
    "MENU_CACHE_HIT_RATE",
    "MENU_CACHE_LOOKUP_TOTAL",
    "record_cache_hit",
    "record_cache_miss",
]
