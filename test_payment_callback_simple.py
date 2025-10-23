#!/usr/bin/env python3
"""
简化的支付回调测试 - 使用已存在的订单
"""
import asyncio
import hmac
import hashlib
import json
import time
import httpx
import os

# 配置
BASE_URL = "http://127.0.0.1:8000"
SECRET_KEY = os.getenv("PERF_SECRET_KEY", "change_me")
ORDER_NUMBER = "20251022212345678-TEST0001"  # 使用一个已存在的订单号

async def create_test_order():
    """先创建一个测试订单"""
    token = os.getenv("PERF_USER_TOKEN", "")
    if token and not token.startswith("Bearer "):
        token = f"Bearer {token}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": token,
        "Idempotency-Key": f"test-payment-{time.time()}"
    }
    
    payload = {
        "items": [{"product_id": 1, "quantity": 1}],
        "order_type": "pickup"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/orders",
            json=payload,
            headers=headers,
            timeout=30.0
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ 订单创建成功: {data['order_number']}, 金额: {data['total_price']}")
            return data['order_number'], data['total_price']
        else:
            print(f"❌ 订单创建失败: {resp.status_code}, {resp.text}")
            return None, None

async def test_payment_callback(order_number: str, amount: float):
    """测试支付回调"""
    payload = {
        "event_id": f"evt_{int(time.time())}",
        "order_number": order_number,
        "transaction_id": f"txn_{int(time.time())}",
        "amount": amount,
        "currency": "CNY",
        "channel": "wechat_jsapi",
        "status": "SUCCESS",
        "paid_at": time.strftime("%Y-%m-%dT%H:%M:%S+0800"),
        "raw_notification": {"test": True}
    }
    
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), body, hashlib.sha256).hexdigest()
    
    headers = {
        "X-Wechat-Signature": signature,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/payments/notify/wechat",
            content=body,
            headers=headers,
            timeout=30.0
        )
        if resp.status_code == 200:
            print(f"✅ 支付回调成功: {resp.json()}")
            return True
        else:
            print(f"❌ 支付回调失败: {resp.status_code}, {resp.text}")
            return False

async def main():
    print("=" * 60)
    print("支付回调单次测试")
    print("=" * 60)
    
    # Step 1: 创建订单
    print("\n[1] 创建测试订单...")
    order_number, amount = await create_test_order()
    
    if not order_number:
        print("无法创建订单，测试终止")
        return
    
    # Step 2: 等待订单提交完成
    print(f"\n[2] 等待1秒确保订单提交...")
    await asyncio.sleep(1)
    
    # Step 3: 发送支付回调
    print(f"\n[3] 发送支付回调...")
    success = await test_payment_callback(order_number, amount)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ 测试通过！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败！")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
