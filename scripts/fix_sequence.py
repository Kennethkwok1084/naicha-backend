#!/usr/bin/env python3
"""修复 orders 表序列不同步问题"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import async_session_factory


async def check_and_fix_sequence():
    """检查并修复 orders 表的序列值"""
    async with async_session_factory() as session:
        try:
            # 1. 检查表中最大 order_id
            result = await session.execute(text("SELECT COALESCE(MAX(order_id), 0) as max_id FROM orders"))
            max_id = result.scalar()
            print(f"📊 orders 表当前最大 order_id: {max_id}")

            # 2. 检查序列当前值
            result = await session.execute(
                text("SELECT last_value FROM orders_order_id_seq")
            )
            seq_value = result.scalar()
            print(f"📊 序列 orders_order_id_seq 当前值: {seq_value}")

            # 3. 判断是否需要修复
            if seq_value <= max_id:
                print(f"\n⚠️  检测到序列不同步！序列值 {seq_value} <= 最大ID {max_id}")
                print(f"🔧 正在修复序列，将设置为 {max_id}...")
                
                # 修复序列：设置为 max_id，true 表示下次 nextval 会返回 max_id + 1
                await session.execute(
                    text(f"SELECT setval('orders_order_id_seq', {max_id}, true)")
                )
                await session.commit()
                
                # 验证修复结果
                result = await session.execute(
                    text("SELECT last_value FROM orders_order_id_seq")
                )
                new_seq_value = result.scalar()
                print(f"✅ 序列已修复！新值: {new_seq_value}")
                print(f"✅ 下次插入将使用 order_id = {new_seq_value + 1}")
            else:
                print(f"\n✅ 序列正常！序列值 {seq_value} > 最大ID {max_id}")
                print(f"✅ 下次插入将使用 order_id = {seq_value + 1}")

            # 4. 检查其他相关表的序列
            tables = [
                ("order_items", "order_items_item_id_seq", "item_id"),
                ("payment_records", "payment_records_pay_id_seq", "pay_id"),
                ("audit_logs", "audit_logs_audit_id_seq", "audit_id"),
                ("print_jobs", "print_jobs_job_id_seq", "job_id"),
                ("want_events", "want_events_id_seq", "id"),
            ]

            print("\n" + "="*60)
            print("检查其他表的序列状态...")
            print("="*60)

            for table_name, seq_name, pk_col in tables:
                try:
                    # 获取最大ID
                    result = await session.execute(
                        text(f"SELECT COALESCE(MAX({pk_col}), 0) as max_id FROM {table_name}")
                    )
                    max_id = result.scalar()

                    # 获取序列值
                    result = await session.execute(text(f"SELECT last_value FROM {seq_name}"))
                    seq_value = result.scalar()

                    status = "⚠️  需要修复" if seq_value <= max_id else "✅ 正常"
                    print(f"{table_name:20} | 最大ID: {max_id:6} | 序列: {seq_value:6} | {status}")

                    # 自动修复
                    if seq_value <= max_id:
                        await session.execute(
                            text(f"SELECT setval('{seq_name}', {max_id}, true)")
                        )
                        print(f"  └─ 已修复 {seq_name} → {max_id}")

                except Exception as e:
                    print(f"{table_name:20} | ❌ 错误: {str(e)}")

            await session.commit()
            print("\n✅ 所有序列检查和修复完成！")

        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_and_fix_sequence())
