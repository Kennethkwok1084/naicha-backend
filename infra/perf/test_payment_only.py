#!/usr/bin/env python3
"""
专门测试支付回调接口的Locust脚本
先通过API创建订单，然后立即发送支付回调通知
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

from locust import HttpUser, between, task


class PaymentNotifyUser(HttpUser):
    """支付回调压测用户"""

    wait_time = between(1.0, 2.0)  # 增加等待时间，避免连接池耗尽

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_headers = {"Content-Type": "application/json"}
        bearer = os.getenv("PERF_USER_TOKEN", "").strip()
        if bearer and not bearer.lower().startswith("bearer "):
            bearer = f"Bearer {bearer}"
        if bearer:
            self._base_headers["Authorization"] = bearer
        self._secret_key = os.getenv("PERF_SECRET_KEY", "")
        if not self._secret_key:
            raise ValueError("PERF_SECRET_KEY 未设置，无法测试支付回调")

    @task
    def create_order_and_notify(self) -> None:
        """创建订单并立即发送支付回调"""
        # 1. 创建订单
        order_payload = {
            "items": [
                {"product_id": 1, "quantity": 2, "customization": "少糖"}
            ],
            "order_type": "pickup",
            "guest_session_id": "guest-perf-001",
            "notes": "Locust支付测试"
        }
        
        headers = dict(self._base_headers)
        headers["Idempotency-Key"] = f"perf-payment-{uuid4()}"
        
        order_resp = self.client.post(
            "/api/v1/orders",
            headers=headers,
            json=order_payload,
            name="CREATE_ORDER_FOR_PAYMENT"
        )
        
        if order_resp.status_code != 200:
            return
        
        order_data = order_resp.json()
        order_number = order_data["order_number"]
        total_price = order_data["total_price"]
        
        # 等待订单提交完成
        time.sleep(0.5)
        
        # 2. 立即发送支付回调
        payment_payload = {
            "event_id": f"evt_{uuid4().hex[:16]}",
            "order_number": order_number,
            "transaction_id": f"txn_{uuid4().hex}",
            "amount": total_price,
            "currency": "CNY",
            "channel": "wechat_jsapi",
            "status": "SUCCESS",
            "paid_at": time.strftime("%Y-%m-%dT%H:%M:%S+0800"),
            "raw_notification": {"source": "locust_test"}
        }
        
        body = json.dumps(payment_payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            self._secret_key.encode("utf-8"), 
            body, 
            hashlib.sha256
        ).hexdigest()
        
        payment_headers = {
            "X-Wechat-Signature": signature,
            "Content-Type": "application/json"
        }
        
        self.client.post(
            "/api/v1/payments/notify/wechat",
            data=body,
            headers=payment_headers,
            name="POST /payments/notify/wechat"
        )
