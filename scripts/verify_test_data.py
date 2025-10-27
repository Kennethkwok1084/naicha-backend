#!/usr/bin/env python3
"""
验证测试数据是否正确填充

用法：
    python scripts/verify_test_data.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import get_settings
from app.models.accounts import Admin, Coupon, LoyaltyTransaction, User, UserAddress
from app.models.catalog import Category, Product, SpecGroup, SpecOption
from app.models.orders import Order, OrderItem, PaymentRecord
from app.models.reservations import ReservationSlot
from app.models.shop import ShopProfile, ShopSetting
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def verify_data() -> bool:
    """验证所有数据"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    all_checks_passed = True
    
    async with session_factory() as session:
        print("=" * 70)
        print("🔍 验证测试数据")
        print("=" * 70)
        print()
        
        # 定义检查项
        checks = [
            ("管理员", Admin, 3),
            ("用户", User, 4),
            ("用户地址", UserAddress, 4),
            ("商品分类", Category, 5),
            ("商品", Product, 10),
            ("规格组", SpecGroup, 4),
            ("规格选项", SpecOption, 17),
            ("订单", Order, 8),
            ("订单项", OrderItem, 12),
            ("支付记录", PaymentRecord, 6),
            ("优惠券", Coupon, 5),
            ("积分记录", LoyaltyTransaction, 9),
            ("预约时段", ReservationSlot, 35),
            ("店铺设置", ShopSetting, 6),
            ("店铺档案", ShopProfile, 1),
        ]
        
        for name, model, expected_count in checks:
            result = await session.execute(select(func.count()).select_from(model))
            actual_count = result.scalar()
            
            if actual_count >= expected_count:
                print(f"✅ {name:12s}: {actual_count:3d} 条 (预期 >= {expected_count})")
            else:
                print(f"❌ {name:12s}: {actual_count:3d} 条 (预期 >= {expected_count})")
                all_checks_passed = False
        
        print()
        
        # 详细检查
        print("📋 详细检查:")
        print()
        
        # 检查管理员账号
        print("👤 管理员账号:")
        result = await session.execute(select(Admin).order_by(Admin.admin_id))
        admins = result.scalars().all()
        for admin in admins:
            print(f"   - {admin.username} ({admin.role})")
        print()
        
        # 检查用户
        print("👥 测试用户:")
        result = await session.execute(select(User).order_by(User.user_id))
        users = result.scalars().all()
        for user in users:
            print(f"   - {user.nickname} (积分: {user.loyalty_points})")
        print()
        
        # 检查商品
        print("🥤 商品列表:")
        result = await session.execute(select(Product).order_by(Product.product_id))
        products = result.scalars().all()
        for product in products:
            status_emoji = "✓" if product.status == "active" else "⊗"
            stock_emoji = "📦" if product.inventory_status == "in_stock" else "❌"
            print(f"   {status_emoji} {stock_emoji} {product.name:12s} - ¥{product.base_price}")
        print()
        
        # 检查订单状态分布
        print("📦 订单状态分布:")
        result = await session.execute(
            select(Order.status, func.count())
            .group_by(Order.status)
            .order_by(Order.status)
        )
        for status, count in result.all():
            print(f"   - {status:20s}: {count} 个")
        print()
        
        # 检查优惠券状态
        print("🎫 优惠券状态:")
        result = await session.execute(
            select(Coupon.status, func.count())
            .group_by(Coupon.status)
            .order_by(Coupon.status)
        )
        for status, count in result.all():
            print(f"   - {status:10s}: {count} 张")
        print()
        
        # 检查店铺设置
        print("⚙️  店铺设置:")
        result = await session.execute(select(ShopSetting).order_by(ShopSetting.key))
        settings_list = result.scalars().all()
        for setting in settings_list:
            print(f"   - {setting.description}: {setting.value}")
        print()
        
        # 检查店铺档案
        print("🏪 店铺档案:")
        result = await session.execute(select(ShopProfile).where(ShopProfile.id == 1))
        shop_profile = result.scalar_one_or_none()
        if shop_profile:
            print(f"   ✓ 营业状态: {'营业中' if shop_profile.is_open else '休息中'}")
            print(f"   ✓ 配送范围: {shop_profile.delivery_radius_m}米")
            print(f"   ✓ 位置: ({shop_profile.location_lat}, {shop_profile.location_lng})")
        else:
            print("   ❌ 店铺档案未创建")
            all_checks_passed = False
        print()
    
    await engine.dispose()
    
    print("=" * 70)
    if all_checks_passed:
        print("✅ 所有检查通过！测试数据完整")
    else:
        print("❌ 部分检查失败，请重新运行填充脚本")
    print("=" * 70)
    print()
    
    return all_checks_passed


async def main() -> None:
    try:
        success = await verify_data()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("💡 常见问题：")
        print("   - 确保数据库正在运行")
        print("   - 检查 DATABASE_URL 环境变量或 .env 文件")
        print("   - 运行 'alembic upgrade head' 确保表已创建")
        print("   - 运行 'python scripts/seed_test_data.py' 创建测试数据")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
