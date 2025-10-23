#!/usr/bin/env python3
"""
创建压测所需的测试数据

用法：
    python scripts/seed_perf_data.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import get_settings
from app.models.accounts import User, Admin
from app.models.catalog import Category, Product
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def seed_test_data() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        print("=" * 70)
        print("🌱 创建压测测试数据")
        print("=" * 70)
        print()

        # 1. 创建测试用户 (user_id=1)
        result = await session.execute(select(User).where(User.user_id == 1))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                user_id=1,
                open_id="test_openid_perf_001",
                nickname="压测用户",
                avatar_url=None,
                loyalty_points=0
            )
            session.add(user)
            await session.flush()
            print(f"✅ 创建测试用户: user_id={user.user_id}, nickname={user.nickname}")
        else:
            print(f"ℹ️  测试用户已存在: user_id={user.user_id}")

        # 2. 创建测试分类
        result = await session.execute(select(Category).where(Category.category_id == 1))
        category = result.scalar_one_or_none()
        
        if not category:
            category = Category(
                category_id=1,
                name="测试分类",
                sort_order=1
            )
            session.add(category)
            await session.flush()
            print(f"✅ 创建测试分类: category_id={category.category_id}, name={category.name}")
        else:
            print(f"ℹ️  测试分类已存在: category_id={category.category_id}")

        # 3. 创建测试商品 (product_id=1)
        result = await session.execute(select(Product).where(Product.product_id == 1))
        product = result.scalar_one_or_none()
        
        if not product:
            product = Product(
                product_id=1,
                category_id=1,
                name="测试商品",
                description="用于压测的测试商品",
                base_price=10.00,
                status="active",
                inventory_status="in_stock"
            )
            session.add(product)
            await session.flush()
            print(f"✅ 创建测试商品: product_id={product.product_id}, name={product.name}, price={product.base_price}")
        else:
            print(f"ℹ️  测试商品已存在: product_id={product.product_id}")

        await session.commit()
        
        print()
        print("=" * 70)
        print("✅ 测试数据创建完成")
        print("=" * 70)
        print()
        print("📋 测试数据摘要:")
        print(f"   User ID: 1 (open_id: test_openid_perf_001)")
        print(f"   Product ID: 1 (价格: ¥10.00, 库存: 9999)")
        print(f"   Category ID: 1")
        print()
        print("🚀 现在可以运行压测了:")
        print("   source .env.perf")
        print("   bash infra/perf/run_baseline.sh")
        print()

    await engine.dispose()


def main() -> None:
    try:
        asyncio.run(seed_test_data())
    except Exception as e:
        print(f"❌ 错误: {e}")
        print()
        print("💡 常见问题：")
        print("   - 确保数据库正在运行")
        print("   - 检查 DATABASE_URL 环境变量或 .env 文件")
        print("   - 运行 'alembic upgrade head' 确保表已创建")
        sys.exit(1)


if __name__ == "__main__":
    main()
