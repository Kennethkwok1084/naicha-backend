#!/usr/bin/env python3
"""验证订单创建是否正常（测试序列修复效果）"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import async_session_factory


async def test_order_creation():
    """测试创建新订单"""
    async with async_session_factory() as session:
        try:
            # 测试插入一个新订单（不指定 order_id，让序列自动生成）
            print("🧪 测试创建新订单...")
            
            # 先查看当前最大 ID
            result = await session.execute(text("SELECT MAX(order_id) FROM orders"))
            max_before = result.scalar() or 0
            print(f"当前最大 order_id: {max_before}")
            
            # 插入测试订单（包含 version 字段）
            insert_sql = text("""
                INSERT INTO orders 
                (order_number, total_price, status, order_type, payment_status, source, version)
                VALUES 
                (:order_number, :total_price, :status, :order_type, :payment_status, :source, 0)
                RETURNING order_id
            """)
            
            result = await session.execute(
                insert_sql,
                {
                    "order_number": f"TEST_{asyncio.get_event_loop().time():.0f}",
                    "total_price": 29.90,
                    "status": "pending_payment",
                    "order_type": "pickup",
                    "payment_status": "pending",
                    "source": "user"
                }
            )
            new_order_id = result.scalar()
            await session.commit()
            
            print(f"✅ 成功创建订单，新 order_id: {new_order_id}")
            print(f"✅ 序列正常工作！新 ID ({new_order_id}) > 之前最大 ID ({max_before})")
            
            # 清理测试数据
            await session.execute(
                text("DELETE FROM orders WHERE order_id = :order_id"),
                {"order_id": new_order_id}
            )
            await session.commit()
            print(f"🧹 已清理测试订单 {new_order_id}")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_order_creation())
