from __future__ import annotations

from prometheus_client import Counter

ADS_CONFIG_REQUEST_TOTAL = Counter(
    "ads_config_request_total",
    "广告配置请求计数",
    ["result"],  # success, version_match, error
)

ADS_EXPOSE_TOTAL = Counter(
    "ads_expose_total",
    "广告曝光打点计数",
    ["slot"],  # HOME_BANNER, HOME_CARD, etc
)

ADS_CLICK_TOTAL = Counter(
    "ads_click_total",
    "广告点击打点计数",
    ["slot"],  # HOME_BANNER, HOME_CARD, etc
)

__all__ = ["ADS_CLICK_TOTAL", "ADS_CONFIG_REQUEST_TOTAL", "ADS_EXPOSE_TOTAL"]
