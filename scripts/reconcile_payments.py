#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.settings import get_settings
from app.db.session import async_session_factory
from app.services.reconciliation import ReconciliationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run order/payment daily reconciliation and surface mismatches.",
    )
    parser.add_argument(
        "--date",
        help="target date to reconcile (YYYY-MM-DD); defaults to previous day",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="force enable CSV export regardless of settings",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with code 1 when differences exist (useful for CI)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="max records to display per difference category",
    )
    return parser.parse_args()


def build_reference(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    target = date.fromisoformat(date_str)
    next_day = target + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=UTC)


def summarize_records(
    title: str,
    records: list[dict[str, Any]],
    limit: int,
) -> None:
    print(f"\n{title}: {len(records)}")
    if not records:
        return
    display = records[: max(limit, 0)]
    for item in display:
        print(f"  - {item}")
    if len(records) > len(display):
        print(f"  ... (remaining {len(records) - len(display)} rows omitted)")


async def run() -> int:
    args = parse_args()
    settings = get_settings()
    reference = build_reference(args.date)

    async with async_session_factory() as session:
        service = ReconciliationService(session, settings)
        result = await service.run_daily(reference=reference, csv_enabled=args.csv or None)

    print("\n=== Reconciliation Summary ===")
    print(f"range: {result.range_start.isoformat()} ~ {result.range_end.isoformat()}")
    print(f"differences: {result.total_differences}")

    summarize_records("orders_missing_payment", result.orders_without_payment, args.limit)
    summarize_records("orders_missing_refund", result.orders_without_refund, args.limit)
    summarize_records("unmatched_payments", result.unmatched_payments, args.limit)

    if result.total_differences == 0:
        print("\n✅ reconciliation clean")
        return 0

    print("\n⚠️ differences detected, manual investigation required")
    return 1 if args.strict else 0


def main() -> None:
    exit_code = asyncio.run(run())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
