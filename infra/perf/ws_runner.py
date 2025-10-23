from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from math import floor
from typing import Any

import websockets


@dataclass
class WsStats:
    connected: int = 0
    failures: int = 0
    timeouts: int = 0
    messages: int = 0
    latencies: list[float] = field(default_factory=list)
    order_notifications: int = 0
    order_validation_errors: int = 0


async def ws_worker(idx: int, args: argparse.Namespace, stats: WsStats, lock: asyncio.Lock) -> None:
    uri = build_ws_url(args.base_url, args.token)
    heartbeat_interval = args.heartbeat_interval
    heartbeat_timeout = args.heartbeat_timeout
    end_ts = time.time() + args.duration
    local_latencies: list[float] = []

    try:
        async with websockets.connect(uri, ping_interval=None, close_timeout=5) as ws:
            async with lock:
                stats.connected += 1

            # 等待初始 ready 消息，但不强制要求
            try:
                initial = await asyncio.wait_for(ws.recv(), timeout=3)
                if initial:
                    async with lock:
                        stats.messages += 1
            except asyncio.TimeoutError:
                pass

            while time.time() < end_ts:
                ping_payload = json.dumps({"type": "ping", "source": idx, "ts": time.time()})
                await ws.send(ping_payload)
                start = time.perf_counter()

                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=heartbeat_timeout)
                        async with lock:
                            stats.messages += 1

                        try:
                            data: dict[str, Any] = json.loads(raw)
                        except json.JSONDecodeError:
                            # 非 JSON 消息直接跳过
                            continue

                        msg_type = data.get("type")
                        if msg_type == "pong":
                            latency_ms = (time.perf_counter() - start) * 1000
                            local_latencies.append(latency_ms)
                            break
                        elif msg_type == "ping":
                            await ws.send(json.dumps({"type": "pong", "source": idx}))
                        elif msg_type == "order.paid":
                            valid = validate_order_broadcast(data)
                            async with lock:
                                stats.order_notifications += 1
                                if not valid:
                                    stats.order_validation_errors += 1
                        else:
                            # 业务广播类消息
                            continue
                except asyncio.TimeoutError:
                    async with lock:
                        stats.timeouts += 1
                    break

                await asyncio.sleep(heartbeat_interval)
    except Exception as e:
        print(f"Worker {idx} error: {type(e).__name__}: {e}")
        async with lock:
            stats.failures += 1
        return

    if local_latencies:
        async with lock:
            stats.latencies.extend(local_latencies)


def build_ws_url(base_url: str, token: str) -> str:
    # 去除 "Bearer " 前缀（如果存在）
    if token.startswith("Bearer "):
        token = token[7:]
    
    separator = "&" if "?" in base_url else "?"
    if "{token}" in base_url:
        return base_url.replace("{token}", token)
    return f"{base_url}{separator}token={token}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Naicha WebSocket 并发校验脚本")
    parser.add_argument("--connections", type=int, default=50, help="并发连接数")
    parser.add_argument("--duration", type=int, default=120, help="测试时长（秒）")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PERF_WS_URL", "ws://127.0.0.1:8000/ws/merchant"),
        help="WebSocket 基础地址",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("PERF_ADMIN_TOKEN"),
        help="管理员 Token（必填）",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=30.0,
        help="心跳间隔（秒）",
    )
    parser.add_argument(
        "--heartbeat-timeout",
        type=float,
        default=5.0,
        help="等待 PONG 的超时时间（秒）",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> WsStats:
    if not args.token:
        raise SystemExit("PERF_ADMIN_TOKEN 未设置，无法建立鉴权连接。")

    stats = WsStats()
    lock = asyncio.Lock()
    workers = [
        asyncio.create_task(ws_worker(i, args, stats, lock))
        for i in range(args.connections)
    ]

    await asyncio.gather(*workers, return_exceptions=False)
    return stats


def summarize(stats: WsStats) -> None:
    print(f"连接成功: {stats.connected}")
    print(f"连接失败: {stats.failures}")
    print(f"PONG 超时: {stats.timeouts}")
    print(f"接收消息: {stats.messages}")
    print(f"订单广播: {stats.order_notifications}")
    if stats.order_validation_errors:
        print(f"订单广播校验失败: {stats.order_validation_errors}")
    lat_sorted = sorted(stats.latencies)
    if not lat_sorted:
        print("未采集到心跳延迟。")
        return
    p50 = percentile(lat_sorted, 50)
    p95 = percentile(lat_sorted, 95)
    p99 = percentile(lat_sorted, 99)
    print(f"P50 (ms): {p50:.2f}")
    print(f"P95 (ms): {p95:.2f}")
    print(f"P99 (ms): {p99:.2f}")


def percentile(sorted_data: list[float], percent: float) -> float:
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return float(sorted_data[0])
    position = (percent / 100) * (len(sorted_data) - 1)
    lower = floor(position)
    upper = min(lower + 1, len(sorted_data) - 1)
    weight = position - lower
    return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight


def validate_order_broadcast(data: dict[str, Any]) -> bool:
    order = data.get("order")
    if not isinstance(order, dict):
        return False
    required_fields = ("order_id", "order_number", "status", "total_price", "paid_at")
    for key in required_fields:
        if key not in order:
            return False
    if not isinstance(order["order_id"], int):
        return False
    if not isinstance(order["order_number"], str):
        return False
    if order["status"] not in {"paid", "settled"}:
        return False
    try:
        float(order["total_price"])
    except (TypeError, ValueError):
        return False
    if not isinstance(order["paid_at"], str):
        return False
    return True


def main() -> None:
    args = parse_args()
    try:
        stats = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n手动终止。", file=sys.stderr)
        return
    summarize(stats)


if __name__ == "__main__":
    main()
