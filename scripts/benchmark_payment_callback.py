#!/usr/bin/env python3
"""支付回调压测脚本,统计延迟分布以评估不同 PRINT_DISPATCH_MODE 策略。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import statistics
import time
from typing import Sequence
from uuid import uuid4

import httpx

DEFAULT_BASE_URL = os.getenv("BENCH_BASE_URL", "http://127.0.0.1:8000")


def _sign(secret_key: str, body: bytes) -> str:
    return hmac.new(secret_key.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _create_guest_session(client: httpx.AsyncClient, base_url: str) -> str:
    resp = await client.post(f"{base_url}/api/v1/guests/session", json={})
    resp.raise_for_status()
    data = resp.json()
    return data["guest_session_id"]


async def _create_order(
    client: httpx.AsyncClient,
    base_url: str,
    guest_session_id: str,
    product_id: int,
    quantity: int,
) -> tuple[str, float]:
    payload = {
        "items": [
            {
                "product_id": product_id,
                "quantity": quantity,
                "spec_option_ids": [],
            }
        ],
        "order_type": "pickup",
        "guest_session_id": guest_session_id,
    }
    headers = {"Idempotency-Key": f"bench-{uuid4()}"}
    resp = await client.post(f"{base_url}/api/v1/orders", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["order_number"], float(data["total_price"])


async def _send_payment_callback(
    client: httpx.AsyncClient,
    base_url: str,
    secret_key: str,
    order_number: str,
    amount: float,
) -> tuple[bool, float, str | None]:
    payload = {
        "event_id": f"evt_{uuid4()}",
        "order_number": order_number,
        "transaction_id": f"txn_{uuid4()}",
        "amount": amount,
        "currency": "CNY",
        "channel": "wechat_jsapi",
        "status": "SUCCESS",
        "paid_at": datetime_now_iso(),
        "raw_notification": {"benchmark": True},
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = _sign(secret_key, body)
    headers = {
        "X-Wechat-Signature": signature,
        "Content-Type": "application/json",
    }
    started = time.perf_counter()
    resp = await client.post(
        f"{base_url}/api/v1/payments/notify/wechat",
        content=body,
        headers=headers,
        timeout=30.0,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    return resp.status_code == 200, latency_ms, None if resp.status_code == 200 else resp.text


def datetime_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


async def run_iteration(
    client: httpx.AsyncClient,
    base_url: str,
    secret_key: str,
    guest_session_id: str,
    product_id: int,
    quantity: int,
) -> tuple[bool, float, str | None]:
    order_number, amount = await _create_order(client, base_url, guest_session_id, product_id, quantity)
    return await _send_payment_callback(client, base_url, secret_key, order_number, amount)


async def benchmark(
    base_url: str,
    secret_key: str,
    iterations: int,
    concurrency: int,
    product_id: int,
    quantity: int,
) -> tuple[Sequence[float], int]:
    latencies: list[float] = []
    failures = 0
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=30.0) as client:
        guest_session_id = await _create_guest_session(client, base_url)

        async def worker(_: int) -> None:
            nonlocal failures
            async with semaphore:
                ok, latency, error = await run_iteration(
                    client, base_url, secret_key, guest_session_id, product_id, quantity
                )
                if ok:
                    latencies.append(latency)
                else:
                    failures += 1
                    print(f"[WARN] callback failed: {error}")

        await asyncio.gather(*(worker(i) for i in range(iterations)))

    return latencies, failures


def percentile(data: Sequence[float], pct: float) -> float:
    if not data:
        return 0.0
    ordered = sorted(data)
    k = (len(ordered) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def summarize(latencies: Sequence[float], failures: int, iterations: int) -> None:
    print("\n=== Payment Callback Benchmark Summary ===")
    print(f"Total Requests: {iterations}")
    print(f"Success: {len(latencies)} | Failures: {failures}")
    if not latencies:
        return
    print(f"Mean: {statistics.mean(latencies):.2f} ms")
    print(f"P50: {percentile(latencies, 0.5):.2f} ms")
    print(f"P95: {percentile(latencies, 0.95):.2f} ms")
    print(f"Max: {max(latencies):.2f} ms")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark payment callback latency")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--secret-key", default=os.getenv("PERF_SECRET_KEY", "change_me"))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--product-id", type=int, default=1)
    parser.add_argument("--quantity", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations <= 0:
        raise SystemExit("iterations must be positive")
    loop = asyncio.get_event_loop()
    latencies, failures = loop.run_until_complete(
        benchmark(
            base_url=args.base_url,
            secret_key=args.secret_key,
            iterations=args.iterations,
            concurrency=max(args.concurrency, 1),
            product_id=args.product_id,
            quantity=args.quantity,
        )
    )
    summarize(latencies, failures, args.iterations)


if __name__ == "__main__":
    main()
