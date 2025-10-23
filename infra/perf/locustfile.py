from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from locust import HttpUser, between, task

DEFAULT_ORDER_TEMPLATE = Path(__file__).with_name("payloads").joinpath("order_template.json")
PAYMENT_CHANNELS = ("wechat_jsapi", "wechat_native")
# 支付回调本应由外部系统触发，通过注入概率控制频率避免占满客户端并发。
PAYMENT_NOTIFY_RATIO = float(os.getenv("PERF_PAYMENT_RATIO", "0.3"))


@dataclass
class PaymentContext:
    order_id: int
    order_number: str
    total_price: float
    channel: str


def load_order_templates(path: str | None) -> list[dict[str, Any]]:
    target = Path(path) if path else DEFAULT_ORDER_TEMPLATE
    if not target.exists():
        raise FileNotFoundError(f"订单模板文件不存在：{target}")
    with target.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list) or not payload:
        raise ValueError("订单模板需为非空数组。")
    return payload


class NaichaUser(HttpUser):
    """核心接口压测任务（菜单、下单、支付回调）。"""

    wait_time = between(0.2, 1.2)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._base_headers: dict[str, str] = {"Content-Type": "application/json"}
        bearer = os.getenv("PERF_USER_TOKEN", "").strip()
        if bearer and not bearer.lower().startswith("bearer "):
            bearer = f"Bearer {bearer}"
        if bearer:
            self._base_headers["Authorization"] = bearer
        self._secret_key = os.getenv("PERF_SECRET_KEY", "")
        if not self._secret_key:
            import logging
            logging.warning("PERF_SECRET_KEY 未设置，支付回调任务将被跳过。")
        self._order_templates = load_order_templates(os.getenv("PERF_ORDER_TEMPLATE"))
        self._recent_orders: list[PaymentContext] = []

    @task(5)
    def fetch_menu(self) -> None:
        self.client.get("/api/v1/menu", name="GET /menu")

    @task(3)
    def create_order(self) -> None:
        template = random.choice(self._order_templates)
        payload = {
            "items": template["items"],
            "order_type": template.get("order_type", "pickup"),
            "notes": template.get("notes"),
            "guest_session_id": template.get("guest_session_id"),
        }
        if template.get("address"):
            payload["address"] = template["address"]

        headers = dict(self._base_headers)
        headers["Idempotency-Key"] = f"perf-{uuid4()}"
        response = self.client.post(
            "/api/v1/orders",
            headers=headers,
            json=payload,
            name="POST /orders",
        )
        # 只在成功创建订单时才添加到回调队列
        if response.status_code != 200:
            import logging
            logging.warning(
                f"订单创建失败 status={response.status_code}, "
                f"不会触发回调: {response.text[:100]}"
            )
            return

        try:
            data = response.json()
            # 验证响应数据完整性
            if not all(k in data for k in ["order_id", "order_number", "total_price"]):
                import logging
                logging.warning(f"订单响应数据不完整，跳过: {data}")
                return
            
            channel = random.choice(PAYMENT_CHANNELS)
            self._recent_orders.append(
                PaymentContext(
                    order_id=data["order_id"],
                    order_number=data["order_number"],
                    total_price=data["total_price"],
                    channel=channel,
                )
            )
            # 限制缓存大小，保留最近的订单
            if len(self._recent_orders) > 100:
                self._recent_orders = self._recent_orders[-50:]
        except (KeyError, ValueError) as e:
            import logging
            logging.error(f"解析订单响应失败: {e}, response={response.text[:100]}")

    @task(1)
    def payment_notify(self) -> None:
        # 前置检查：密钥和订单队列
        if not self._secret_key:
            return
        if not self._recent_orders:
            return

        # 按配置的概率触发回调
        if random.random() > PAYMENT_NOTIFY_RATIO:
            return

        target = random.choice(self._recent_orders)
        
        # 构造回调载荷
        payload = {
            "event_id": f"evt_{uuid4().hex[:16]}",
            "order_number": target.order_number,
            "transaction_id": f"txn_{uuid4().hex}",
            "amount": target.total_price,
            "currency": "CNY",
            "channel": target.channel,
            "status": "SUCCESS",
            "paid_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "raw_notification": {"debug": True, "locust_test": True},
        }

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._secret_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers = {"X-Wechat-Signature": signature, "Content-Type": "application/json"}

        result = self.client.post(
            "/api/v1/payments/notify/wechat",
            data=body,
            headers=headers,
            name="POST /payments/notify/wechat",
            catch_response=True,
        )
        
        # 详细错误日志
        if result.status_code == 404:
            import logging
            try:
                error_detail = result.json().get("detail", "Unknown")
                logging.warning(
                    f"支付回调 404: order_number={target.order_number}, "
                    f"detail={error_detail}"
                )
                # 如果是订单不存在，从队列移除该订单
                if "not found" in error_detail.lower():
                    self._recent_orders.remove(target)
                    result.failure(f"订单不存在: {target.order_number}")
            except Exception:
                logging.error(f"支付回调 404，无法解析响应: {result.text[:100]}")
                result.failure("支付回调 404")
        elif result.status_code == 200:
            result.success()
        else:
            import logging
            logging.warning(
                f"支付回调异常: status={result.status_code}, "
                f"order={target.order_number}, response={result.text[:100]}"
            )
            result.failure(f"HTTP {result.status_code}")
