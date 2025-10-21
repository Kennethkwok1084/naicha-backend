#!/usr/bin/env python3
"""
Week1 压测结果解析脚本
用途：解析 Locust CSV、wrk 输出、WS 日志，自动填充到 doc/perf-baseline.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class LocustMetrics:
    """Locust 单接口指标"""

    method: str
    endpoint: str
    concurrent: int
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    error_rate: float = 0.0
    qps: float = 0.0
    note: str = ""


@dataclass
class WrkMetrics:
    """wrk 基线指标"""

    script: str
    params: str
    qps: float = 0.0
    avg_latency_ms: float = 0.0
    p95_ms: float = 0.0
    success_rate: float = 100.0
    note: str = ""


@dataclass
class WsMetrics:
    """WebSocket 指标"""

    connections: int
    duration: int
    heartbeat_p95: float = 0.0
    heartbeat_p99: float = 0.0
    broadcast_count: int = 0
    broadcast_failures: int = 0
    note: str = ""


@dataclass
class PerformanceReport:
    """完整的性能报告"""

    timestamp: str
    locust_metrics: list[LocustMetrics] = field(default_factory=list)
    wrk_metrics: list[WrkMetrics] = field(default_factory=list)
    ws_metrics: WsMetrics | None = None
    prometheus_snapshot: dict[str, Any] = field(default_factory=dict)


def parse_locust_stats(csv_path: Path, concurrent: int) -> list[LocustMetrics]:
    """解析 Locust CSV 统计文件"""
    metrics = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            if not name or name == "Aggregated":
                continue

            # 解析方法和路径
            parts = name.split(" ", 1)
            method = parts[0] if len(parts) > 1 else "GET"
            endpoint = parts[1] if len(parts) > 1 else name

            try:
                p50 = float(row.get("50%", 0))
                p95 = float(row.get("95%", 0))
                p99 = float(row.get("99%", 0))
                failures = int(row.get("Failure Count", 0))
                requests = int(row.get("Request Count", 0))
                qps = float(row.get("Requests/s", 0))

                error_rate = (failures / requests * 100) if requests > 0 else 0.0

                metrics.append(
                    LocustMetrics(
                        method=method,
                        endpoint=endpoint,
                        concurrent=concurrent,
                        p50=p50,
                        p95=p95,
                        p99=p99,
                        error_rate=error_rate,
                        qps=qps,
                    )
                )
            except (ValueError, KeyError) as e:
                print(f"⚠️  跳过解析行: {name}, 错误: {e}", file=sys.stderr)
                continue

    return metrics


def parse_wrk_output(wrk_path: Path) -> list[WrkMetrics]:
    """解析 wrk 输出文件"""
    metrics = []

    if not wrk_path.exists():
        return metrics

    content = wrk_path.read_text(encoding="utf-8")

    # 简单正则匹配 wrk 结果
    # Requests/sec:   1234.56
    # Latency    50.00ms   80.00ms  100.00ms  95.00%
    qps_match = re.search(r"Requests/sec:\s+([\d.]+)", content)
    latency_match = re.search(
        r"Latency\s+([\d.]+\w+)\s+([\d.]+\w+)\s+([\d.]+\w+)\s+([\d.]+)%", content
    )

    if qps_match:
        qps = float(qps_match.group(1))
        avg_latency = 0.0
        p95 = 0.0

        if latency_match:
            # 解析延迟单位
            avg_str = latency_match.group(1)
            p95_str = latency_match.group(3)
            avg_latency = parse_latency_to_ms(avg_str)
            p95 = parse_latency_to_ms(p95_str)

        metrics.append(
            WrkMetrics(
                script="menu.lua",
                params="-t4 -c100 -d30s",
                qps=qps,
                avg_latency_ms=avg_latency,
                p95_ms=p95,
            )
        )

    return metrics


def parse_latency_to_ms(latency_str: str) -> float:
    """将 wrk 延迟字符串转换为毫秒"""
    value = re.search(r"([\d.]+)", latency_str)
    if not value:
        return 0.0

    num = float(value.group(1))
    if "us" in latency_str:
        return num / 1000
    elif "ms" in latency_str:
        return num
    elif "s" in latency_str:
        return num * 1000
    return num


def parse_ws_output(ws_path: Path) -> WsMetrics | None:
    """解析 WebSocket 输出"""
    if not ws_path.exists():
        return None

    content = ws_path.read_text(encoding="utf-8")

    # 连接成功: 200
    # P50 (ms): 15.23
    # P95 (ms): 45.67
    # P99 (ms): 89.12
    # 订单广播: 123
    # 订单广播校验失败: 0

    connections_match = re.search(r"连接成功:\s+(\d+)", content)
    p50_match = re.search(r"P50 \(ms\):\s+([\d.]+)", content)
    p95_match = re.search(r"P95 \(ms\):\s+([\d.]+)", content)
    p99_match = re.search(r"P99 \(ms\):\s+([\d.]+)", content)
    broadcast_match = re.search(r"订单广播:\s+(\d+)", content)
    failures_match = re.search(r"订单广播校验失败:\s+(\d+)", content)

    if not connections_match:
        return None

    return WsMetrics(
        connections=int(connections_match.group(1)),
        duration=120,
        heartbeat_p95=float(p95_match.group(1)) if p95_match else 0.0,
        heartbeat_p99=float(p99_match.group(1)) if p99_match else 0.0,
        broadcast_count=int(broadcast_match.group(1)) if broadcast_match else 0,
        broadcast_failures=int(failures_match.group(1)) if failures_match else 0,
    )


def update_baseline_doc(report: PerformanceReport, baseline_path: Path) -> None:
    """更新 perf-baseline.md 文档"""

    if not baseline_path.exists():
        print(f"❌ 基线文档不存在: {baseline_path}", file=sys.stderr)
        return

    content = baseline_path.read_text(encoding="utf-8")

    # 更新填写人和时间
    content = re.sub(
        r"(> 填写人：)待补充",
        f"\\g<1>{report.timestamp}",
        content,
    )
    content = re.sub(
        r"(> 上次更新：)待补充",
        f"\\g<1>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        content,
    )

    # 更新 Locust 表格
    for metric in report.locust_metrics:
        endpoint_pattern = re.escape(f"{metric.method} {metric.endpoint}")
        pattern = rf"(\|\s*{metric.concurrent}\s*\|\s*{endpoint_pattern}\s*\|)\s*待填\s*\|\s*待填\s*\|\s*待填\s*\|\s*待填\s*\|\s*待填\s*\|"

        replacement = f"\\g<1> {metric.p50:.1f} | {metric.p95:.1f} | {metric.p99:.1f} | {metric.error_rate:.2f}% | {metric.qps:.1f} |"
        content = re.sub(pattern, replacement, content)

    # 更新 WebSocket 表格
    if report.ws_metrics:
        ws = report.ws_metrics
        ws_pattern = r"(\|\s*\d+\s*\|\s*\d+\s*\|)\s*待填\s*\|\s*待填\s*\|\s*待填\s*\|\s*待填\s*\|"
        ws_replacement = f"\\g<1> {ws.heartbeat_p95:.1f} | {ws.heartbeat_p99:.1f} | {ws.broadcast_count} | {ws.broadcast_failures} |"
        content = re.sub(ws_pattern, ws_replacement, content, count=1)

    # 写回文件
    baseline_path.write_text(content, encoding="utf-8")
    print(f"✅ 已更新基线文档: {baseline_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="解析压测结果并更新 perf-baseline.md")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("./perf_results"),
        help="压测结果目录",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("./doc/perf-baseline.md"),
        help="perf-baseline.md 路径",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="导出 JSON 报告路径（可选）",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ 输入目录不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 解析压测结果: {args.input}")

    # 收集所有结果文件
    locust_files = list(args.input.glob("locust_*_stats.csv"))
    wrk_files = list(args.input.glob("wrk_*.txt"))
    ws_files = list(args.input.glob("ws_*.txt"))

    report = PerformanceReport(timestamp=datetime.now().isoformat())

    # 解析 Locust
    print(f"📊 发现 {len(locust_files)} 个 Locust 结果文件")
    for csv_file in locust_files:
        # 从文件名提取并发数 locust_100u_20250421_120000_stats.csv
        match = re.search(r"locust_(\d+)u_", csv_file.name)
        if match:
            concurrent = int(match.group(1))
            metrics = parse_locust_stats(csv_file, concurrent)
            report.locust_metrics.extend(metrics)
            print(f"  ✅ 解析完成: {csv_file.name} (并发={concurrent})")

    # 解析 wrk
    if wrk_files:
        print(f"📊 发现 {len(wrk_files)} 个 wrk 结果文件")
        for wrk_file in wrk_files:
            metrics = parse_wrk_output(wrk_file)
            report.wrk_metrics.extend(metrics)
            print(f"  ✅ 解析完成: {wrk_file.name}")

    # 解析 WebSocket
    if ws_files:
        print(f"📊 发现 {len(ws_files)} 个 WebSocket 结果文件")
        ws_metrics = parse_ws_output(ws_files[0])
        if ws_metrics:
            report.ws_metrics = ws_metrics
            print(f"  ✅ 解析完成: {ws_files[0].name}")

    # 更新基线文档
    if args.baseline.exists():
        update_baseline_doc(report, args.baseline)
    else:
        print(f"⚠️  基线文档不存在，跳过更新: {args.baseline}")

    # 导出 JSON（可选）
    if args.output_json:
        output_data = {
            "timestamp": report.timestamp,
            "locust": [
                {
                    "method": m.method,
                    "endpoint": m.endpoint,
                    "concurrent": m.concurrent,
                    "p50": m.p50,
                    "p95": m.p95,
                    "p99": m.p99,
                    "error_rate": m.error_rate,
                    "qps": m.qps,
                }
                for m in report.locust_metrics
            ],
            "wrk": [
                {
                    "script": w.script,
                    "params": w.params,
                    "qps": w.qps,
                    "avg_latency_ms": w.avg_latency_ms,
                    "p95_ms": w.p95_ms,
                }
                for w in report.wrk_metrics
            ],
            "websocket": (
                {
                    "connections": report.ws_metrics.connections,
                    "duration": report.ws_metrics.duration,
                    "heartbeat_p95": report.ws_metrics.heartbeat_p95,
                    "heartbeat_p99": report.ws_metrics.heartbeat_p99,
                    "broadcast_count": report.ws_metrics.broadcast_count,
                    "broadcast_failures": report.ws_metrics.broadcast_failures,
                }
                if report.ws_metrics
                else None
            ),
        }

        args.output_json.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
        print(f"✅ JSON 报告已导出: {args.output_json}")

    print("")
    print("========================================")
    print("✅ 解析完成")
    print("========================================")
    print(f"Locust 指标: {len(report.locust_metrics)} 条")
    print(f"wrk 指标: {len(report.wrk_metrics)} 条")
    print(f"WebSocket 指标: {'已解析' if report.ws_metrics else '未发现'}")
    print("")


if __name__ == "__main__":
    main()
