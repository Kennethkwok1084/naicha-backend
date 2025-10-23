#!/usr/bin/env python3
"""
支付回调诊断脚本

用途：
1. 验证订单是否成功创建并落库
2. 测试支付回调是否能正确找到订单
3. 区分路由 404 和业务 404

用法：
    python scripts/test_payment_callback.py
    python scripts/test_payment_callback.py --order-number ORD20250122123456
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("PERF_SECRET_KEY", "")
USER_TOKEN = os.getenv("PERF_USER_TOKEN", "")


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def create_test_order(client: httpx.AsyncClient) -> dict | None:
    """创建测试订单"""
    print_section("步骤 1: 创建测试订单")
    
    payload = {
        "items": [
            {
                "product_id": 1,
                "quantity": 1,
                "specs": [],
                "notes": "测试订单 - 支付回调诊断",
            }
        ],
        "order_type": "pickup",
        "notes": f"诊断测试 {time.strftime('%Y%m%d%H%M%S')}",
    }
    
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": f"diag-{uuid4()}",
    }
    
    if USER_TOKEN:
        if not USER_TOKEN.lower().startswith("bearer "):
            headers["Authorization"] = f"Bearer {USER_TOKEN}"
        else:
            headers["Authorization"] = USER_TOKEN
    
    try:
        response = await client.post(
            f"{API_BASE}/api/v1/orders",
            json=payload,
            headers=headers,
            timeout=10.0,
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ 订单创建成功")
            print(f"    订单号: {data['order_number']}")
            print(f"    订单ID: {data['order_id']}")
            print(f"    总金额: {data['total_price']}")
            return data
        else:
            print(f"  ✗ 订单创建失败")
            print(f"    响应: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  ✗ 请求异常: {e}")
        return None


async def test_payment_callback(
    client: httpx.AsyncClient,
    order_number: str,
    total_price: float,
) -> dict | None:
    """测试支付回调"""
    print_section("步骤 2: 发送支付回调")
    
    if not SECRET_KEY:
        print("  ✗ PERF_SECRET_KEY 未设置，无法生成签名")
        return None
    
    payload = {
        "event_id": f"evt_{uuid4().hex[:16]}",
        "order_number": order_number,
        "transaction_id": f"txn_diag_{uuid4().hex}",
        "amount": total_price,
        "currency": "CNY",
        "channel": "wechat_jsapi",
        "status": "SUCCESS",
        "paid_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "raw_notification": {"debug": True, "source": "diagnostic_script"},
    }
    
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    headers = {
        "X-Wechat-Signature": signature,
        "Content-Type": "application/json",
    }
    
    print(f"  订单号: {order_number}")
    print(f"  金额: {total_price}")
    print(f"  交易ID: {payload['transaction_id']}")
    
    try:
        response = await client.post(
            f"{API_BASE}/api/v1/payments/notify/wechat",
            content=body,
            headers=headers,
            timeout=10.0,
        )
        
        print(f"\n  状态码: {response.status_code}")
        
        if response.status_code == 200:
            print(f"  ✓ 回调处理成功")
            print(f"    响应: {response.json()}")
            return response.json()
        else:
            print(f"  ✗ 回调处理失败")
            try:
                error_detail = response.json()
                print(f"    错误类型: {error_detail.get('detail', 'N/A')}")
            except Exception:
                print(f"    响应文本: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  ✗ 请求异常: {e}")
        return None


async def verify_order_in_db(order_number: str) -> None:
    """通过 API 验证订单是否存在"""
    print_section("步骤 3: 验证订单状态")
    
    print(f"  提示: 可手动查询数据库确认订单 {order_number} 是否存在")
    print(f"  SQL: SELECT * FROM orders WHERE order_number = '{order_number}';")


async def main() -> int:
    parser = argparse.ArgumentParser(description="支付回调诊断工具")
    parser.add_argument(
        "--order-number",
        help="使用已存在的订单号进行测试",
    )
    parser.add_argument(
        "--amount",
        type=float,
        help="订单金额（与 --order-number 配合使用）",
    )
    args = parser.parse_args()
    
    print_section("支付回调诊断 - 开始")
    print(f"  API 地址: {API_BASE}")
    print(f"  密钥配置: {'✓' if SECRET_KEY else '✗ 未配置'}")
    print(f"  用户令牌: {'✓' if USER_TOKEN else '✗ 未配置（可能需要）'}")
    
    async with httpx.AsyncClient() as client:
        if args.order_number:
            order_number = args.order_number
            total_price = args.amount or 10.0
            print(f"\n使用现有订单: {order_number}")
        else:
            order_data = await create_test_order(client)
            if not order_data:
                print("\n✗ 无法创建测试订单，终止诊断")
                return 1
            
            order_number = order_data["order_number"]
            total_price = order_data["total_price"]
            
            # 等待订单落库
            print(f"\n  等待 1 秒确保订单落库...")
            await asyncio.sleep(1)
        
        callback_result = await test_payment_callback(
            client,
            order_number,
            total_price,
        )
        
        await verify_order_in_db(order_number)
        
        print_section("诊断总结")
        if callback_result:
            print("  ✓ 支付回调流程正常")
            return 0
        else:
            print("  ✗ 支付回调出现问题")
            print("\n可能的原因:")
            print("  1. 订单未成功落库（检查订单创建接口日志）")
            print("  2. 并发压测时订单创建失败但仍被加入 _recent_orders")
            print("  3. 数据库事务未提交导致订单对回调不可见")
            print("  4. 签名验证失败（检查 PERF_SECRET_KEY 配置）")
            print("\n建议操作:")
            print("  - 查看应用日志中的 'payment.notification_received' 和 'payment.order_not_found'")
            print("  - 检查数据库中是否存在该订单号")
            print("  - 降低压测中的 PERF_PAYMENT_RATIO 参数")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
