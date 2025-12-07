#!/usr/bin/env python3
"""
创建完整的测试数据，用于前端开发和后端测试

用法：
    python scripts/seed_test_data.py
    
    # 清空现有数据并重新填充
    python scripts/seed_test_data.py --clean
    
功能：
    - 创建管理员账号
    - 创建测试用户和地址
    - 创建商品分类和商品
    - 创建规格组和规格选项
    - 创建测试订单（不同状态）
    - 创建优惠券和积分记录
    - 创建店铺设置和配置
    - 创建预约时段
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import get_settings
from app.db.base import Base
from app.models.accounts import Admin, Coupon, LoyaltyTransaction, User, UserAddress
from app.models.advertisement import AdCreative, AdPlacement, AdSlot
from app.models.catalog import (
    Category,
    Product,
    ProductCategory,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.models.orders import Order, OrderItem, PaymentRecord
from app.models.reservations import ReservationSlot
from app.models.shop import ShopConfig, ShopProfile, ShopSetting
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def sync_sequences(session_factory) -> None:
    """同步所有主键序列，避免手动指定ID后序列不更新导致的主键冲突"""
    async with session_factory() as session:
        print("🔧 同步数据库序列...")
        
        tables = [
            ("orders", "orders_order_id_seq", "order_id"),
            ("order_items", "order_items_item_id_seq", "item_id"),
            ("payment_records", "payment_records_pay_id_seq", "pay_id"),
            ("audit_logs", "audit_logs_audit_id_seq", "audit_id"),
            ("print_jobs", "print_jobs_job_id_seq", "job_id"),
            ("want_events", "want_events_id_seq", "id"),
            ("users", "users_user_id_seq", "user_id"),
            ("user_addresses", "user_addresses_address_id_seq", "address_id"),
            ("admins", "admins_admin_id_seq", "admin_id"),
            ("categories", "categories_category_id_seq", "category_id"),
            ("products", "products_product_id_seq", "product_id"),
            ("spec_groups", "spec_groups_group_id_seq", "group_id"),
            ("spec_options", "spec_options_option_id_seq", "option_id"),
            ("coupons", "coupons_coupon_id_seq", "coupon_id"),
            ("loyalty_transactions", "loyalty_transactions_transaction_id_seq", "transaction_id"),
            ("reservation_slots", "reservation_slots_slot_id_seq", "slot_id"),
            ("ad_slots", "ad_slots_slot_id_seq", "slot_id"),
            ("ad_creatives", "ad_creatives_creative_id_seq", "creative_id"),
            ("ad_placements", "ad_placements_placement_id_seq", "placement_id"),
        ]
        
        for table_name, seq_name, pk_col in tables:
            try:
                # 获取最大ID
                result = await session.execute(
                    text(f"SELECT COALESCE(MAX({pk_col}), 0) as max_id FROM {table_name}")
                )
                max_id = result.scalar()
                
                # 同步序列
                if max_id > 0:
                    await session.execute(text(f"SELECT setval('{seq_name}', {max_id}, true)"))
                    print(f"  ✓ {table_name:25} 序列已同步至 {max_id}")
            except Exception as e:
                # 某些表可能不存在或没有序列，跳过
                pass
        
        await session.commit()
        print()


async def clean_database(session_factory) -> None:
    """清空所有数据"""
    async with session_factory() as session:
        print("🗑️  清空现有数据...")
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
        print("✅ 数据已清空\n")


async def seed_admins(session_factory) -> None:
    """创建管理员账号"""
    async with session_factory() as session:
        print("👤 创建管理员账号...")
        
        admins_data = [
            {
                "admin_id": 1,
                "username": "admin",
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq",  # password: admin123
                "role": "admin"
            },
            {
                "admin_id": 2,
                "username": "manager",
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq",  # password: admin123
                "role": "manager"
            },
            {
                "admin_id": 3,
                "username": "clerk",
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq",  # password: admin123
                "role": "clerk"
            }
        ]
        
        for admin_data in admins_data:
            result = await session.execute(
                select(Admin).where(Admin.admin_id == admin_data["admin_id"])
            )
            if not result.scalar_one_or_none():
                session.add(Admin(**admin_data))
                print(f"  ✓ {admin_data['username']} ({admin_data['role']})")
        
        await session.commit()
        print()


async def seed_users(session_factory) -> None:
    """创建测试用户"""
    async with session_factory() as session:
        print("👥 创建测试用户...")
        
        users_data = [
            {
                "user_id": 1,
                "open_id": "test_openid_001",
                "nickname": "张三",
                "avatar_url": "https://via.placeholder.com/100",
                "loyalty_points": 100,
                "preferences_json": {"favorite_sugar": "正常糖", "favorite_ice": "少冰"}
            },
            {
                "user_id": 2,
                "open_id": "test_openid_002",
                "nickname": "李四",
                "avatar_url": "https://via.placeholder.com/100",
                "loyalty_points": 250,
                "preferences_json": {"favorite_sugar": "半糖", "favorite_ice": "去冰"}
            },
            {
                "user_id": 3,
                "open_id": "test_openid_003",
                "nickname": "王五",
                "avatar_url": "https://via.placeholder.com/100",
                "loyalty_points": 50,
                "preferences_json": None
            },
            {
                "user_id": 4,
                "open_id": "test_openid_004",
                "nickname": "赵六",
                "avatar_url": None,
                "loyalty_points": 0,
                "preferences_json": None
            }
        ]
        
        for user_data in users_data:
            result = await session.execute(
                select(User).where(User.user_id == user_data["user_id"])
            )
            if not result.scalar_one_or_none():
                session.add(User(**user_data))
                print(f"  ✓ {user_data['nickname']} (积分: {user_data['loyalty_points']})")
        
        await session.commit()
        print()


async def seed_user_addresses(session_factory) -> None:
    """创建用户地址"""
    async with session_factory() as session:
        print("📍 创建用户地址...")
        
        addresses_data = [
            {
                "address_id": 1,
                "user_id": 1,
                "contact_name": "张三",
                "phone": "13800138001",
                "address_line": "北京市朝阳区建国路1号",
                "lat": 39.9075,
                "lng": 116.3972,
                "is_default": True
            },
            {
                "address_id": 2,
                "user_id": 1,
                "contact_name": "张三",
                "phone": "13800138001",
                "address_line": "北京市海淀区中关村大街1号",
                "lat": 39.9833,
                "lng": 116.3139,
                "is_default": False
            },
            {
                "address_id": 3,
                "user_id": 2,
                "contact_name": "李四",
                "phone": "13800138002",
                "address_line": "上海市浦东新区陆家嘴环路1000号",
                "lat": 31.2397,
                "lng": 121.4993,
                "is_default": True
            },
            {
                "address_id": 4,
                "user_id": 3,
                "contact_name": "王五",
                "phone": "13800138003",
                "address_line": "广州市天河区天河路208号",
                "lat": 23.1353,
                "lng": 113.3223,
                "is_default": True
            }
        ]
        
        for addr_data in addresses_data:
            result = await session.execute(
                select(UserAddress).where(UserAddress.address_id == addr_data["address_id"])
            )
            if not result.scalar_one_or_none():
                session.add(UserAddress(**addr_data))
                print(f"  ✓ {addr_data['contact_name']}: {addr_data['address_line'][:30]}...")
        
        await session.commit()
        print()


async def seed_categories(session_factory) -> None:
    """创建商品分类"""
    async with session_factory() as session:
        print("📂 创建商品分类...")
        
        categories_data = [
            {"category_id": 1, "name": "奶茶系列", "sort_order": 1},
            {"category_id": 2, "name": "果茶系列", "sort_order": 2},
            {"category_id": 3, "name": "咖啡系列", "sort_order": 3},
            {"category_id": 4, "name": "甜品系列", "sort_order": 4},
            {"category_id": 5, "name": "季节限定", "sort_order": 5}
        ]
        
        for cat_data in categories_data:
            result = await session.execute(
                select(Category).where(Category.category_id == cat_data["category_id"])
            )
            if not result.scalar_one_or_none():
                session.add(Category(**cat_data))
                print(f"  ✓ {cat_data['name']}")
        
        await session.commit()
        print()


async def seed_products(session_factory) -> None:
    """创建商品"""
    async with session_factory() as session:
        print("🥤 创建商品...")
        
        products_data = [
            # 奶茶系列
            {
                "product_id": 1,
                "category_id": 1,
                "name": "珍珠奶茶",
                "description": "经典珍珠奶茶，香滑浓郁",
                "image_url": "https://via.placeholder.com/300?text=珍珠奶茶",
                "base_price": Decimal("15.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 100
            },
            {
                "product_id": 2,
                "category_id": 1,
                "name": "波霸奶茶",
                "description": "Q弹波霸，口感升级",
                "image_url": "https://via.placeholder.com/300?text=波霸奶茶",
                "base_price": Decimal("16.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 80
            },
            {
                "product_id": 3,
                "category_id": 1,
                "name": "布丁奶茶",
                "description": "香滑布丁配奶茶",
                "image_url": "https://via.placeholder.com/300?text=布丁奶茶",
                "base_price": Decimal("17.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 60
            },
            # 果茶系列
            {
                "product_id": 4,
                "category_id": 2,
                "name": "水果茶",
                "description": "新鲜水果与茶的完美结合",
                "image_url": "https://via.placeholder.com/300?text=水果茶",
                "base_price": Decimal("18.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 50
            },
            {
                "product_id": 5,
                "category_id": 2,
                "name": "柠檬茶",
                "description": "清新柠檬，酸甜可口",
                "image_url": "https://via.placeholder.com/300?text=柠檬茶",
                "base_price": Decimal("14.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 70
            },
            {
                "product_id": 6,
                "category_id": 2,
                "name": "芒果冰沙",
                "description": "浓郁芒果，冰爽夏日",
                "image_url": "https://via.placeholder.com/300?text=芒果冰沙",
                "base_price": Decimal("20.00"),
                "status": "active",
                "inventory_status": "sold_out",
                "stock_quantity": 0
            },
            # 咖啡系列
            {
                "product_id": 7,
                "category_id": 3,
                "name": "美式咖啡",
                "description": "经典美式，提神醒脑",
                "image_url": "https://via.placeholder.com/300?text=美式咖啡",
                "base_price": Decimal("16.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 90
            },
            {
                "product_id": 8,
                "category_id": 3,
                "name": "拿铁咖啡",
                "description": "香浓奶香与咖啡的融合",
                "image_url": "https://via.placeholder.com/300?text=拿铁咖啡",
                "base_price": Decimal("18.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 85
            },
            {
                "product_id": 9,
                "category_id": 3,
                "name": "摩卡咖啡",
                "description": "巧克力与咖啡的甜蜜邂逅",
                "image_url": "https://via.placeholder.com/300?text=摩卡咖啡",
                "base_price": Decimal("19.00"),
                "status": "inactive",
                "inventory_status": "in_stock",
                "stock_quantity": 40
            },
            # 甜品系列
            {
                "product_id": 10,
                "category_id": 4,
                "name": "芝士蛋糕",
                "description": "浓郁芝士，入口即化",
                "image_url": "https://via.placeholder.com/300?text=芝士蛋糕",
                "base_price": Decimal("25.00"),
                "status": "active",
                "inventory_status": "in_stock",
                "stock_quantity": 30
            }
        ]
        
        for prod_data in products_data:
            result = await session.execute(
                select(Product).where(Product.product_id == prod_data["product_id"])
            )
            if not result.scalar_one_or_none():
                session.add(Product(**prod_data))
                status_emoji = "✓" if prod_data["status"] == "active" else "⊗"
                stock_emoji = "📦" if prod_data["inventory_status"] == "in_stock" else "❌"
                print(f"  {status_emoji} {stock_emoji} {prod_data['name']} - ¥{prod_data['base_price']}")
        
        await session.commit()
        print()


async def seed_product_categories(session_factory) -> None:
    """创建商品分类关联"""
    async with session_factory() as session:
        print("🔗 创建商品分类关联...")
        
        # 为所有商品关联其分类
        mappings_data = [
            {"product_id": 1, "category_id": 1},
            {"product_id": 2, "category_id": 1},
            {"product_id": 3, "category_id": 1},
            {"product_id": 4, "category_id": 2},
            {"product_id": 5, "category_id": 2},
            {"product_id": 6, "category_id": 2},
            {"product_id": 7, "category_id": 3},
            {"product_id": 8, "category_id": 3},
            {"product_id": 9, "category_id": 3},
            {"product_id": 10, "category_id": 4},
            # 季节限定 - 部分商品同时属于多个分类
            {"product_id": 6, "category_id": 5},
        ]
        
        for mapping_data in mappings_data:
            result = await session.execute(
                select(ProductCategory).where(
                    ProductCategory.product_id == mapping_data["product_id"],
                    ProductCategory.category_id == mapping_data["category_id"]
                )
            )
            if not result.scalar_one_or_none():
                session.add(ProductCategory(**mapping_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(mappings_data)} 个关联")
        print()


async def seed_spec_groups_and_options(session_factory) -> None:
    """创建规格组和规格选项"""
    async with session_factory() as session:
        print("🎨 创建规格组和选项...")
        
        # 规格组
        spec_groups_data = [
            {"group_id": 1, "name": "糖度", "sort_order": 1},
            {"group_id": 2, "name": "冰度", "sort_order": 2},
            {"group_id": 3, "name": "杯型", "sort_order": 3},
            {"group_id": 4, "name": "加料", "sort_order": 4}
        ]
        
        for group_data in spec_groups_data:
            result = await session.execute(
                select(SpecGroup).where(SpecGroup.group_id == group_data["group_id"])
            )
            if not result.scalar_one_or_none():
                session.add(SpecGroup(**group_data))
                print(f"  ✓ 规格组: {group_data['name']}")
        
        await session.flush()
        
        # 规格选项
        spec_options_data = [
            # 糖度选项
            {"option_id": 1, "group_id": 1, "name": "正常糖", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 1},
            {"option_id": 2, "group_id": 1, "name": "七分糖", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 2},
            {"option_id": 3, "group_id": 1, "name": "半糖", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 3},
            {"option_id": 4, "group_id": 1, "name": "三分糖", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 4},
            {"option_id": 5, "group_id": 1, "name": "无糖", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 5},
            # 冰度选项
            {"option_id": 6, "group_id": 2, "name": "正常冰", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 1},
            {"option_id": 7, "group_id": 2, "name": "少冰", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 2},
            {"option_id": 8, "group_id": 2, "name": "去冰", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 3},
            {"option_id": 9, "group_id": 2, "name": "热饮", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 4},
            # 杯型选项
            {"option_id": 10, "group_id": 3, "name": "中杯", "price_modifier": Decimal("0.00"), "inventory_status": "in_stock", "sort_order": 1},
            {"option_id": 11, "group_id": 3, "name": "大杯", "price_modifier": Decimal("3.00"), "inventory_status": "in_stock", "sort_order": 2},
            {"option_id": 12, "group_id": 3, "name": "超大杯", "price_modifier": Decimal("5.00"), "inventory_status": "in_stock", "sort_order": 3},
            # 加料选项
            {"option_id": 13, "group_id": 4, "name": "珍珠", "price_modifier": Decimal("2.00"), "inventory_status": "in_stock", "sort_order": 1},
            {"option_id": 14, "group_id": 4, "name": "椰果", "price_modifier": Decimal("2.00"), "inventory_status": "in_stock", "sort_order": 2},
            {"option_id": 15, "group_id": 4, "name": "布丁", "price_modifier": Decimal("3.00"), "inventory_status": "in_stock", "sort_order": 3},
            {"option_id": 16, "group_id": 4, "name": "仙草", "price_modifier": Decimal("2.00"), "inventory_status": "sold_out", "sort_order": 4},
            {"option_id": 17, "group_id": 4, "name": "芋圆", "price_modifier": Decimal("3.00"), "inventory_status": "in_stock", "sort_order": 5}
        ]
        
        for option_data in spec_options_data:
            result = await session.execute(
                select(SpecOption).where(SpecOption.option_id == option_data["option_id"])
            )
            if not result.scalar_one_or_none():
                session.add(SpecOption(**option_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(spec_options_data)} 个规格选项")
        print()


async def seed_product_spec_mappings(session_factory) -> None:
    """创建商品规格映射"""
    async with session_factory() as session:
        print("🔗 创建商品规格映射...")
        
        # 为饮品类商品添加规格
        mappings_data = []
        
        # 产品 1-9 (饮品) 都有糖度、冰度、杯型选项
        for product_id in range(1, 10):
            mappings_data.extend([
                {"product_id": product_id, "group_id": 1},  # 糖度
                {"product_id": product_id, "group_id": 2},  # 冰度
                {"product_id": product_id, "group_id": 3},  # 杯型
            ])
        
        # 产品 1-3 (奶茶系列) 可以加料
        for product_id in range(1, 4):
            mappings_data.append({"product_id": product_id, "group_id": 4})  # 加料
        
        # 为每个映射分配 ID
        for idx, mapping_data in enumerate(mappings_data, start=1):
            mapping_data["mapping_id"] = idx
            result = await session.execute(
                select(ProductSpecMapping).where(
                    ProductSpecMapping.product_id == mapping_data["product_id"],
                    ProductSpecMapping.group_id == mapping_data["group_id"]
                )
            )
            if not result.scalar_one_or_none():
                session.add(ProductSpecMapping(**mapping_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(mappings_data)} 个商品规格映射")
        print()


async def seed_shop_settings(session_factory) -> None:
    """创建店铺设置"""
    async with session_factory() as session:
        print("⚙️  创建店铺设置...")
        
        settings_data = [
            {
                "key": "shop_name",
                "value": "奶茶小站",
                "description": "店铺名称"
            },
            {
                "key": "shop_phone",
                "value": "400-123-4567",
                "description": "店铺电话"
            },
            {
                "key": "shop_address",
                "value": "北京市朝阳区建国路88号",
                "description": "店铺地址"
            },
            {
                "key": "min_delivery_amount",
                "value": "20.00",
                "description": "最低配送金额"
            },
            {
                "key": "delivery_fee",
                "value": "5.00",
                "description": "配送费"
            },
            {
                "key": "free_delivery_amount",
                "value": "50.00",
                "description": "免配送费金额"
            }
        ]
        
        for setting_data in settings_data:
            result = await session.execute(
                select(ShopSetting).where(ShopSetting.key == setting_data["key"])
            )
            if not result.scalar_one_or_none():
                session.add(ShopSetting(**setting_data))
                print(f"  ✓ {setting_data['description']}: {setting_data['value']}")
        
        await session.commit()
        print()


async def seed_shop_profile(session_factory) -> None:
    """创建店铺档案"""
    async with session_factory() as session:
        print("🏪 创建店铺档案...")
        
        result = await session.execute(select(ShopProfile).where(ShopProfile.id == 1))
        if not result.scalar_one_or_none():
            shop_profile = ShopProfile(
                id=1,
                is_open=True,
                open_hours_json={
                    "monday": {"open": "09:00", "close": "22:00"},
                    "tuesday": {"open": "09:00", "close": "22:00"},
                    "wednesday": {"open": "09:00", "close": "22:00"},
                    "thursday": {"open": "09:00", "close": "22:00"},
                    "friday": {"open": "09:00", "close": "23:00"},
                    "saturday": {"open": "09:00", "close": "23:00"},
                    "sunday": {"open": "10:00", "close": "22:00"}
                },
                location_lat=39.9075,
                location_lng=116.3972,
                delivery_radius_m=5000,
                timezone="Asia/Shanghai"
            )
            session.add(shop_profile)
            await session.commit()
            print("  ✓ 店铺档案已创建")
        else:
            print("  ℹ️  店铺档案已存在")
        print()


async def seed_reservation_slots(session_factory) -> None:
    """创建预约时段"""
    async with session_factory() as session:
        print("📅 创建预约时段...")
        
        # 创建未来7天的预约时段
        now = datetime.now()
        slots_data = []
        
        for day_offset in range(7):
            base_date = now + timedelta(days=day_offset)
            # 每天 4 个时段：上午、中午、下午、晚上
            time_slots = [
                (10, 12, 10),  # 10:00-12:00, 容量10
                (12, 14, 15),  # 12:00-14:00, 容量15
                (14, 16, 12),  # 14:00-16:00, 容量12
                (16, 18, 10),  # 16:00-18:00, 容量10
                (18, 20, 8),   # 18:00-20:00, 容量8
            ]
            
            for start_hour, end_hour, capacity in time_slots:
                slot_start = base_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                slot_end = base_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
                
                slots_data.append({
                    "slot_start": slot_start,
                    "slot_end": slot_end,
                    "capacity": capacity,
                    "reserved_count": 0
                })
        
        for slot_data in slots_data:
            result = await session.execute(
                select(ReservationSlot).where(
                    ReservationSlot.slot_start == slot_data["slot_start"]
                )
            )
            if not result.scalar_one_or_none():
                session.add(ReservationSlot(**slot_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(slots_data)} 个预约时段")
        print()


async def seed_orders(session_factory) -> None:
    """创建测试订单"""
    async with session_factory() as session:
        print("📦 创建测试订单...")
        
        now = datetime.now()
        
        orders_data = [
            # 已支付待制作订单
            {
                "order_id": 1,
                "order_number": "ON20231001001",
                "user_id": 1,
                "guest_session_id": None,
                "total_price": Decimal("35.00"),
                "notes": "少冰少糖",
                "status": "paid",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": "wechat_jsapi",
                "payment_status": "paid",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": "A001",
                "created_at": now - timedelta(minutes=5)
            },
            # 制作中订单
            {
                "order_id": 2,
                "order_number": "ON20231001002",
                "user_id": 2,
                "guest_session_id": None,
                "total_price": Decimal("52.00"),
                "notes": "多加珍珠",
                "status": "in_production",
                "order_type": "delivery",
                "address_json": {
                    "contact_name": "李四",
                    "phone": "13800138002",
                    "address_line": "上海市浦东新区陆家嘴环路1000号",
                    "lat": 31.2397,
                    "lng": 121.4993
                },
                "payment_channel": "wechat_native",
                "payment_status": "paid",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": "A002",
                "created_at": now - timedelta(minutes=15)
            },
            # 待取货订单
            {
                "order_id": 3,
                "order_number": "ON20231001003",
                "user_id": 1,
                "guest_session_id": None,
                "total_price": Decimal("18.00"),
                "notes": None,
                "status": "ready_for_pickup",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": "wechat_jsapi",
                "payment_status": "paid",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": "B001",
                "created_at": now - timedelta(minutes=30)
            },
            # 已完成订单
            {
                "order_id": 4,
                "order_number": "ON20231001004",
                "user_id": 3,
                "guest_session_id": None,
                "total_price": Decimal("44.00"),
                "notes": "尽快配送",
                "status": "completed",
                "order_type": "delivery",
                "address_json": {
                    "contact_name": "王五",
                    "phone": "13800138003",
                    "address_line": "广州市天河区天河路208号",
                    "lat": 23.1353,
                    "lng": 113.3223
                },
                "payment_channel": "wechat_jsapi",
                "payment_status": "paid",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": None,
                "created_at": now - timedelta(hours=2)
            },
            # 待支付订单
            {
                "order_id": 5,
                "order_number": "ON20231001005",
                "user_id": 1,
                "guest_session_id": None,
                "total_price": Decimal("25.00"),
                "notes": None,
                "status": "pending_payment",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": None,
                "payment_status": "pending",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": None,
                "created_at": now - timedelta(minutes=10)
            },
            # 已取消订单
            {
                "order_id": 6,
                "order_number": "ON20231001006",
                "user_id": 2,
                "guest_session_id": None,
                "total_price": Decimal("30.00"),
                "notes": None,
                "status": "cancelled",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": None,
                "payment_status": "pending",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": None,
                "created_at": now - timedelta(hours=1)
            },
            # POS 订单（管理员创建）
            {
                "order_id": 7,
                "order_number": "ON20231001007",
                "user_id": None,
                "guest_session_id": None,
                "total_price": Decimal("40.00"),
                "notes": "店内点单",
                "status": "completed",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": "static_qr",
                "payment_status": "paid",
                "source": "pos",
                "created_by_admin_id": 1,
                "is_scheduled": False,
                "scheduled_at": None,
                "pickup_code": "C001",
                "created_at": now - timedelta(hours=3)
            },
            # 预约订单
            {
                "order_id": 8,
                "order_number": "ON20231001008",
                "user_id": 3,
                "guest_session_id": None,
                "total_price": Decimal("60.00"),
                "notes": "明天下午取",
                "status": "paid",
                "order_type": "pickup",
                "address_json": None,
                "payment_channel": "wechat_jsapi",
                "payment_status": "paid",
                "source": "user",
                "created_by_admin_id": None,
                "is_scheduled": True,
                "scheduled_at": now + timedelta(days=1, hours=2),
                "pickup_code": "D001",
                "created_at": now - timedelta(hours=5)
            }
        ]
        
        for order_data in orders_data:
            result = await session.execute(
                select(Order).where(Order.order_id == order_data["order_id"])
            )
            if not result.scalar_one_or_none():
                session.add(Order(**order_data))
                print(f"  ✓ {order_data['order_number']} - {order_data['status']} - ¥{order_data['total_price']}")
        
        await session.commit()
        print()


async def seed_order_items(session_factory) -> None:
    """创建订单项"""
    async with session_factory() as session:
        print("📝 创建订单项...")
        
        items_data = [
            # 订单1的商品
            {
                "item_id": 1,
                "order_id": 1,
                "product_id": 1,
                "product_name": "珍珠奶茶",
                "quantity": 2,
                "unit_price": Decimal("15.00"),
                "selected_specs_json": {
                    "糖度": "半糖",
                    "冰度": "少冰",
                    "杯型": "大杯"
                }
            },
            {
                "item_id": 2,
                "order_id": 1,
                "product_id": 5,
                "product_name": "柠檬茶",
                "quantity": 1,
                "unit_price": Decimal("14.00"),
                "selected_specs_json": {
                    "糖度": "正常糖",
                    "冰度": "去冰",
                    "杯型": "中杯"
                }
            },
            # 订单2的商品
            {
                "item_id": 3,
                "order_id": 2,
                "product_id": 1,
                "product_name": "珍珠奶茶",
                "quantity": 2,
                "unit_price": Decimal("20.00"),
                "selected_specs_json": {
                    "糖度": "正常糖",
                    "冰度": "正常冰",
                    "杯型": "大杯",
                    "加料": "珍珠,布丁"
                }
            },
            {
                "item_id": 4,
                "order_id": 2,
                "product_id": 7,
                "product_name": "美式咖啡",
                "quantity": 1,
                "unit_price": Decimal("16.00"),
                "selected_specs_json": {
                    "糖度": "无糖",
                    "冰度": "正常冰",
                    "杯型": "中杯"
                }
            },
            # 订单3的商品
            {
                "item_id": 5,
                "order_id": 3,
                "product_id": 4,
                "product_name": "水果茶",
                "quantity": 1,
                "unit_price": Decimal("18.00"),
                "selected_specs_json": {
                    "糖度": "七分糖",
                    "冰度": "少冰",
                    "杯型": "中杯"
                }
            },
            # 订单4的商品
            {
                "item_id": 6,
                "order_id": 4,
                "product_id": 2,
                "product_name": "波霸奶茶",
                "quantity": 2,
                "unit_price": Decimal("19.00"),
                "selected_specs_json": {
                    "糖度": "半糖",
                    "冰度": "少冰",
                    "杯型": "大杯"
                }
            },
            {
                "item_id": 7,
                "order_id": 4,
                "product_id": 5,
                "product_name": "柠檬茶",
                "quantity": 1,
                "unit_price": Decimal("14.00"),
                "selected_specs_json": {
                    "糖度": "三分糖",
                    "冰度": "去冰",
                    "杯型": "中杯"
                }
            },
            # 订单5的商品
            {
                "item_id": 8,
                "order_id": 5,
                "product_id": 10,
                "product_name": "芝士蛋糕",
                "quantity": 1,
                "unit_price": Decimal("25.00"),
                "selected_specs_json": None
            },
            # 订单6的商品
            {
                "item_id": 9,
                "order_id": 6,
                "product_id": 1,
                "product_name": "珍珠奶茶",
                "quantity": 2,
                "unit_price": Decimal("15.00"),
                "selected_specs_json": {
                    "糖度": "正常糖",
                    "冰度": "正常冰",
                    "杯型": "中杯"
                }
            },
            # 订单7的商品
            {
                "item_id": 10,
                "order_id": 7,
                "product_id": 8,
                "product_name": "拿铁咖啡",
                "quantity": 2,
                "unit_price": Decimal("18.00"),
                "selected_specs_json": {
                    "糖度": "正常糖",
                    "冰度": "热饮",
                    "杯型": "中杯"
                }
            },
            {
                "item_id": 11,
                "order_id": 7,
                "product_id": 10,
                "product_name": "芝士蛋糕",
                "quantity": 1,
                "unit_price": Decimal("25.00"),
                "selected_specs_json": None
            },
            # 订单8的商品
            {
                "item_id": 12,
                "order_id": 8,
                "product_id": 1,
                "product_name": "珍珠奶茶",
                "quantity": 3,
                "unit_price": Decimal("20.00"),
                "selected_specs_json": {
                    "糖度": "半糖",
                    "冰度": "少冰",
                    "杯型": "超大杯"
                }
            }
        ]
        
        for item_data in items_data:
            result = await session.execute(
                select(OrderItem).where(OrderItem.item_id == item_data["item_id"])
            )
            if not result.scalar_one_or_none():
                session.add(OrderItem(**item_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(items_data)} 个订单项")
        print()


async def seed_payment_records(session_factory) -> None:
    """创建支付记录"""
    async with session_factory() as session:
        print("💰 创建支付记录...")
        
        now = datetime.now()
        
        payment_records_data = [
            {
                "pay_id": 1,
                "record_type": "payment",
                "channel": "wechat_jsapi",
                "currency": "CNY",
                "amount": Decimal("35.00"),
                "txn_id": "WX20231001001",
                "out_trade_no": "ON20231001001",
                "qr_session_id": None,
                "matched_order_id": 1,
                "match_status": "auto_matched",
                "matched_by_admin_id": None,
                "match_confidence": Decimal("1.0000"),
                "paid_at": now - timedelta(minutes=5),
                "raw_notification_json": {"transaction_id": "WX20231001001"}
            },
            {
                "pay_id": 2,
                "record_type": "payment",
                "channel": "wechat_native",
                "currency": "CNY",
                "amount": Decimal("52.00"),
                "txn_id": "WX20231001002",
                "out_trade_no": "ON20231001002",
                "qr_session_id": None,
                "matched_order_id": 2,
                "match_status": "auto_matched",
                "matched_by_admin_id": None,
                "match_confidence": Decimal("1.0000"),
                "paid_at": now - timedelta(minutes=15),
                "raw_notification_json": {"transaction_id": "WX20231001002"}
            },
            {
                "pay_id": 3,
                "record_type": "payment",
                "channel": "wechat_jsapi",
                "currency": "CNY",
                "amount": Decimal("18.00"),
                "txn_id": "WX20231001003",
                "out_trade_no": "ON20231001003",
                "qr_session_id": None,
                "matched_order_id": 3,
                "match_status": "auto_matched",
                "matched_by_admin_id": None,
                "match_confidence": Decimal("1.0000"),
                "paid_at": now - timedelta(minutes=30),
                "raw_notification_json": {"transaction_id": "WX20231001003"}
            },
            {
                "pay_id": 4,
                "record_type": "payment",
                "channel": "wechat_jsapi",
                "currency": "CNY",
                "amount": Decimal("44.00"),
                "txn_id": "WX20231001004",
                "out_trade_no": "ON20231001004",
                "qr_session_id": None,
                "matched_order_id": 4,
                "match_status": "auto_matched",
                "matched_by_admin_id": None,
                "match_confidence": Decimal("1.0000"),
                "paid_at": now - timedelta(hours=2),
                "raw_notification_json": {"transaction_id": "WX20231001004"}
            },
            {
                "pay_id": 5,
                "record_type": "payment",
                "channel": "static_qr",
                "currency": "CNY",
                "amount": Decimal("40.00"),
                "txn_id": "WX20231001007",
                "out_trade_no": None,
                "qr_session_id": "qr_session_001",
                "matched_order_id": 7,
                "match_status": "manual_matched",
                "matched_by_admin_id": 1,
                "match_confidence": Decimal("0.8500"),
                "paid_at": now - timedelta(hours=3),
                "raw_notification_json": {"transaction_id": "WX20231001007"}
            },
            {
                "pay_id": 6,
                "record_type": "payment",
                "channel": "wechat_jsapi",
                "currency": "CNY",
                "amount": Decimal("60.00"),
                "txn_id": "WX20231001008",
                "out_trade_no": "ON20231001008",
                "qr_session_id": None,
                "matched_order_id": 8,
                "match_status": "auto_matched",
                "matched_by_admin_id": None,
                "match_confidence": Decimal("1.0000"),
                "paid_at": now - timedelta(hours=5),
                "raw_notification_json": {"transaction_id": "WX20231001008"}
            }
        ]
        
        for payment_data in payment_records_data:
            result = await session.execute(
                select(PaymentRecord).where(PaymentRecord.pay_id == payment_data["pay_id"])
            )
            if not result.scalar_one_or_none():
                session.add(PaymentRecord(**payment_data))
                print(f"  ✓ {payment_data['channel']} - ¥{payment_data['amount']} - {payment_data['match_status']}")
        
        await session.commit()
        print()


async def seed_coupons(session_factory) -> None:
    """创建优惠券"""
    async with session_factory() as session:
        print("🎫 创建优惠券...")
        
        now = datetime.now()
        
        coupons_data = [
            # 用户1的优惠券
            {
                "coupon_id": 1,
                "user_id": 1,
                "type": "free_any_drink",
                "status": "active",
                "meta_json": {"max_price": 20.00},
                "issued_at": now - timedelta(days=5),
                "used_at": None,
                "used_in_order_id": None
            },
            {
                "coupon_id": 2,
                "user_id": 1,
                "type": "free_any_drink",
                "status": "used",
                "meta_json": {"max_price": 20.00},
                "issued_at": now - timedelta(days=10),
                "used_at": now - timedelta(hours=2),
                "used_in_order_id": 4
            },
            # 用户2的优惠券
            {
                "coupon_id": 3,
                "user_id": 2,
                "type": "free_any_drink",
                "status": "active",
                "meta_json": {"max_price": 20.00},
                "issued_at": now - timedelta(days=3),
                "used_at": None,
                "used_in_order_id": None
            },
            {
                "coupon_id": 4,
                "user_id": 2,
                "type": "free_any_drink",
                "status": "active",
                "meta_json": {"max_price": 20.00},
                "issued_at": now - timedelta(days=7),
                "used_at": None,
                "used_in_order_id": None
            },
            # 用户3的优惠券
            {
                "coupon_id": 5,
                "user_id": 3,
                "type": "free_any_drink",
                "status": "expired",
                "meta_json": {"max_price": 20.00},
                "issued_at": now - timedelta(days=60),
                "used_at": None,
                "used_in_order_id": None
            }
        ]
        
        for coupon_data in coupons_data:
            result = await session.execute(
                select(Coupon).where(Coupon.coupon_id == coupon_data["coupon_id"])
            )
            if not result.scalar_one_or_none():
                session.add(Coupon(**coupon_data))
                print(f"  ✓ User {coupon_data['user_id']} - {coupon_data['type']} - {coupon_data['status']}")
        
        await session.commit()
        print()


async def seed_loyalty_transactions(session_factory) -> None:
    """创建积分交易记录"""
    async with session_factory() as session:
        print("⭐ 创建积分交易记录...")
        
        transactions_data = [
            # 用户1的积分记录
            {"id": 1, "user_id": 1, "order_id": 1, "delta_points": 35, "reason": "order_paid"},
            {"id": 2, "user_id": 1, "order_id": 3, "delta_points": 18, "reason": "order_paid"},
            {"id": 3, "user_id": 1, "order_id": None, "delta_points": 50, "reason": "coupon_grant"},
            # 用户2的积分记录
            {"id": 4, "user_id": 2, "order_id": 2, "delta_points": 52, "reason": "order_paid"},
            {"id": 5, "user_id": 2, "order_id": None, "delta_points": 100, "reason": "coupon_grant"},
            {"id": 6, "user_id": 2, "order_id": None, "delta_points": 100, "reason": "coupon_grant"},
            # 用户3的积分记录
            {"id": 7, "user_id": 3, "order_id": 4, "delta_points": 44, "reason": "order_paid"},
            {"id": 8, "user_id": 3, "order_id": 8, "delta_points": 60, "reason": "order_paid"},
            {"id": 9, "user_id": 3, "order_id": None, "delta_points": -50, "reason": "coupon_use"}
        ]
        
        for trans_data in transactions_data:
            result = await session.execute(
                select(LoyaltyTransaction).where(LoyaltyTransaction.id == trans_data["id"])
            )
            if not result.scalar_one_or_none():
                session.add(LoyaltyTransaction(**trans_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(transactions_data)} 条积分交易记录")
        print()


async def seed_ad_slots(session_factory) -> None:
    """创建广告位"""
    async with session_factory() as session:
        print("🎪 创建广告位...")
        
        slots_data = [
            {
                "slot_id": 1,
                "code": "home_banner",
                "name": "首页轮播图",
                "description": "小程序首页顶部轮播广告位",
                "spec": {"width": 750, "height": 400, "max_items": 5}
            },
            {
                "slot_id": 2,
                "code": "category_top",
                "name": "分类页顶部",
                "description": "商品分类页面顶部横幅",
                "spec": {"width": 750, "height": 300, "max_items": 3}
            },
            {
                "slot_id": 3,
                "code": "order_success",
                "name": "下单成功页",
                "description": "订单支付成功后展示的广告",
                "spec": {"width": 750, "height": 200, "max_items": 1}
            }
        ]
        
        for slot_data in slots_data:
            result = await session.execute(
                select(AdSlot).where(AdSlot.slot_id == slot_data["slot_id"])
            )
            if not result.scalar_one_or_none():
                session.add(AdSlot(**slot_data))
                print(f"  ✓ {slot_data['name']} ({slot_data['code']})")
        
        await session.commit()
        print()


async def seed_ad_creatives(session_factory) -> None:
    """创建广告素材"""
    async with session_factory() as session:
        print("🖼️  创建广告素材...")
        
        now = datetime.now()
        
        creatives_data = [
            {
                "creative_id": 1,
                "title": "新品上市 - 芝士奶盖",
                "image_url": "https://via.placeholder.com/750x400?text=芝士奶盖新品",
                "jump_type": "miniapp_page",
                "jump_payload": {"page": "/pages/product/detail", "product_id": 1},
                "start_time": now - timedelta(days=5),
                "end_time": now + timedelta(days=25),
                "enabled": True,
                "priority": 100,
                "platforms": ["miniapp"],
                "tags": ["新品", "热门"]
            },
            {
                "creative_id": 2,
                "title": "夏日特饮 - 冰爽柠檬茶",
                "image_url": "https://via.placeholder.com/750x400?text=柠檬茶特惠",
                "jump_type": "miniapp_page",
                "jump_payload": {"page": "/pages/product/detail", "product_id": 5},
                "start_time": now - timedelta(days=10),
                "end_time": now + timedelta(days=20),
                "enabled": True,
                "priority": 90,
                "platforms": ["miniapp"],
                "tags": ["促销"]
            },
            {
                "creative_id": 3,
                "title": "会员日专享",
                "image_url": "https://via.placeholder.com/750x400?text=会员专享",
                "jump_type": "miniapp_page",
                "jump_payload": {"page": "/pages/user/coupons"},
                "start_time": now - timedelta(days=2),
                "end_time": now + timedelta(days=28),
                "enabled": True,
                "priority": 80,
                "platforms": ["miniapp"],
                "tags": ["会员"]
            },
            {
                "creative_id": 4,
                "title": "甜品系列上新",
                "image_url": "https://via.placeholder.com/750x300?text=甜品上新",
                "jump_type": "miniapp_page",
                "jump_payload": {"page": "/pages/category/list", "category_id": 4},
                "start_time": now - timedelta(days=1),
                "end_time": now + timedelta(days=14),
                "enabled": True,
                "priority": 70,
                "platforms": ["miniapp"],
                "tags": ["甜品"]
            },
            {
                "creative_id": 5,
                "title": "下单立享优惠",
                "image_url": "https://via.placeholder.com/750x200?text=下单优惠",
                "jump_type": "miniapp_page",
                "jump_payload": {"page": "/pages/index/index"},
                "start_time": now,
                "end_time": now + timedelta(days=30),
                "enabled": True,
                "priority": 60,
                "platforms": ["miniapp"],
                "tags": ["优惠"]
            },
            {
                "creative_id": 6,
                "title": "过期广告示例",
                "image_url": "https://via.placeholder.com/750x400?text=已过期",
                "jump_type": "none",
                "jump_payload": None,
                "start_time": now - timedelta(days=60),
                "end_time": now - timedelta(days=30),
                "enabled": False,
                "priority": 50,
                "platforms": ["miniapp"],
                "tags": ["测试"]
            }
        ]
        
        for creative_data in creatives_data:
            result = await session.execute(
                select(AdCreative).where(AdCreative.creative_id == creative_data["creative_id"])
            )
            if not result.scalar_one_or_none():
                session.add(AdCreative(**creative_data))
                status = "✓" if creative_data["enabled"] else "⊗"
                print(f"  {status} {creative_data['title']} (优先级: {creative_data['priority']})")
        
        await session.commit()
        print()


async def seed_ad_placements(session_factory) -> None:
    """创建广告投放"""
    async with session_factory() as session:
        print("🔗 创建广告投放...")
        
        placements_data = [
            # 首页轮播图
            {"placement_id": 1, "slot_code": "home_banner", "creative_id": 1, "sort_order": 1},
            {"placement_id": 2, "slot_code": "home_banner", "creative_id": 2, "sort_order": 2},
            {"placement_id": 3, "slot_code": "home_banner", "creative_id": 3, "sort_order": 3},
            # 分类页顶部
            {"placement_id": 4, "slot_code": "category_top", "creative_id": 4, "sort_order": 1},
            {"placement_id": 5, "slot_code": "category_top", "creative_id": 1, "sort_order": 2},
            # 下单成功页
            {"placement_id": 6, "slot_code": "order_success", "creative_id": 5, "sort_order": 1}
        ]
        
        for placement_data in placements_data:
            result = await session.execute(
                select(AdPlacement).where(AdPlacement.placement_id == placement_data["placement_id"])
            )
            if not result.scalar_one_or_none():
                session.add(AdPlacement(**placement_data))
        
        await session.commit()
        print(f"  ✓ 创建了 {len(placements_data)} 个广告投放")
        print()


async def seed_shop_config(session_factory) -> None:
    """创建店铺配置"""
    async with session_factory() as session:
        print("⚙️  创建店铺功能配置...")
        
        configs_data = [
            {
                "config_key": "features.disable_delivery",
                "value_json": False,
                "category": "features",
                "description": "紧急关闭外卖配送"
            },
            {
                "config_key": "features.disable_coupons",
                "value_json": False,
                "category": "features",
                "description": "临时关闭优惠券功能"
            },
            {
                "config_key": "features.disable_stamps",
                "value_json": False,
                "category": "features",
                "description": "临时关闭集点功能"
            }
        ]
        
        for config_data in configs_data:
            result = await session.execute(
                select(ShopConfig).where(ShopConfig.config_key == config_data["config_key"])
            )
            if not result.scalar_one_or_none():
                session.add(ShopConfig(**config_data))
                status = "🟢" if not config_data["value_json"] else "🔴"
                print(f"  {status} {config_data['description']}: {config_data['value_json']}")
        
        await session.commit()
        print()


async def main() -> None:
    parser = argparse.ArgumentParser(description="创建测试数据")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="清空现有数据后重新创建"
    )
    args = parser.parse_args()
    
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    try:
        print("=" * 70)
        print("🌱 奶茶后端测试数据填充")
        print("=" * 70)
        print()
        
        if args.clean:
            await clean_database(session_factory)
        
        # 按依赖顺序创建数据
        await seed_admins(session_factory)
        await seed_users(session_factory)
        await seed_user_addresses(session_factory)
        await seed_categories(session_factory)
        await seed_products(session_factory)
        await seed_product_categories(session_factory)
        await seed_spec_groups_and_options(session_factory)
        await seed_product_spec_mappings(session_factory)
        await seed_shop_settings(session_factory)
        await seed_shop_profile(session_factory)
        await seed_shop_config(session_factory)
        await seed_reservation_slots(session_factory)
        await seed_orders(session_factory)
        await seed_order_items(session_factory)
        await seed_payment_records(session_factory)
        await seed_coupons(session_factory)
        await seed_loyalty_transactions(session_factory)
        await seed_ad_slots(session_factory)
        await seed_ad_creatives(session_factory)
        await seed_ad_placements(session_factory)
        
        # 同步所有主键序列（避免后续插入时主键冲突）
        await sync_sequences(session_factory)
        
        print("=" * 70)
        print("✅ 所有测试数据创建完成！")
        print("=" * 70)
        print()
        print("📋 数据摘要:")
        print("   👤 管理员: 3 个 (admin, manager, clerk)")
        print("   👥 用户: 4 个")
        print("   📍 地址: 4 个")
        print("   📂 分类: 5 个")
        print("   🥤 商品: 10 个")
        print("   🎨 规格组: 4 个 (糖度/冰度/杯型/加料)")
        print("   📦 订单: 8 个 (不同状态，含取餐码)")
        print("   💰 支付记录: 6 条")
        print("   🎫 优惠券: 5 张")
        print("   ⭐ 积分记录: 9 条")
        print("   📅 预约时段: 35 个 (未来7天)")
        print("   🎪 广告位: 3 个")
        print("   🖼️  广告素材: 6 个")
        print("   🔗 广告投放: 6 个")
        print("   ⚙️  店铺配置: 3 个功能开关")
        print()
        print("🔐 测试账号:")
        print("   管理员: admin / admin123")
        print("   管理员: manager / admin123")
        print("   管理员: clerk / admin123")
        print()
        print("🚀 可以开始开发和测试了！")
        print()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("💡 常见问题：")
        print("   - 确保数据库正在运行")
        print("   - 检查 DATABASE_URL 环境变量或 .env 文件")
        print("   - 运行 'alembic upgrade head' 确保表已创建")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
