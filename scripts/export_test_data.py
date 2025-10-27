#!/usr/bin/env python3
"""
导出测试数据到 SQL 文件

用法：
    python scripts/export_test_data.py
    python scripts/export_test_data.py --output test_data.sql
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import get_settings
from app.models.accounts import Admin, Coupon, LoyaltyTransaction, User, UserAddress
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
from app.models.shop import ShopProfile, ShopSetting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def format_value(value) -> str:
    """格式化 SQL 值"""
    if value is None:
        return "NULL"
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    elif isinstance(value, dict):
        import json
        return f"'{json.dumps(value, ensure_ascii=False)}'"
    else:
        # 转义单引号
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"


def generate_insert(table_name: str, data: dict) -> str:
    """生成 INSERT 语句"""
    columns = ", ".join(data.keys())
    values = ", ".join(format_value(v) for v in data.values())
    return f"INSERT INTO {table_name} ({columns}) VALUES ({values});"


async def export_data(output_file: str) -> None:
    """导出数据到 SQL 文件"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入文件头
        f.write("-- 奶茶后端测试数据\n")
        f.write(f"-- 生成时间: {datetime.now().isoformat()}\n")
        f.write("-- 警告: 仅用于开发和测试环境\n")
        f.write("\n")
        f.write("BEGIN;\n\n")
        
        async with session_factory() as session:
            print("📝 正在导出数据到 SQL 文件...")
            print()
            
            # 管理员
            print("  导出管理员...")
            f.write("-- 管理员\n")
            result = await session.execute(select(Admin).order_by(Admin.admin_id))
            for admin in result.scalars():
                data = {
                    "admin_id": admin.admin_id,
                    "username": admin.username,
                    "password_hash": admin.password_hash,
                    "role": admin.role,
                    "created_at": admin.created_at,
                }
                f.write(generate_insert("admins", data) + "\n")
            f.write("\n")
            
            # 用户
            print("  导出用户...")
            f.write("-- 用户\n")
            result = await session.execute(select(User).order_by(User.user_id))
            for user in result.scalars():
                data = {
                    "user_id": user.user_id,
                    "open_id": user.open_id,
                    "nickname": user.nickname,
                    "avatar_url": user.avatar_url,
                    "loyalty_points": user.loyalty_points,
                    "preferences_json": user.preferences_json,
                    "created_at": user.created_at,
                }
                f.write(generate_insert("users", data) + "\n")
            f.write("\n")
            
            # 用户地址
            print("  导出用户地址...")
            f.write("-- 用户地址\n")
            result = await session.execute(select(UserAddress).order_by(UserAddress.address_id))
            for addr in result.scalars():
                data = {
                    "address_id": addr.address_id,
                    "user_id": addr.user_id,
                    "contact_name": addr.contact_name,
                    "phone": addr.phone,
                    "address_line": addr.address_line,
                    "lat": addr.lat,
                    "lng": addr.lng,
                    "is_default": addr.is_default,
                    "created_at": addr.created_at,
                    "updated_at": addr.updated_at,
                }
                f.write(generate_insert("user_addresses", data) + "\n")
            f.write("\n")
            
            # 分类
            print("  导出商品分类...")
            f.write("-- 商品分类\n")
            result = await session.execute(select(Category).order_by(Category.category_id))
            for cat in result.scalars():
                data = {
                    "category_id": cat.category_id,
                    "name": cat.name,
                    "sort_order": cat.sort_order,
                    "created_at": cat.created_at,
                }
                f.write(generate_insert("categories", data) + "\n")
            f.write("\n")
            
            # 商品
            print("  导出商品...")
            f.write("-- 商品\n")
            result = await session.execute(select(Product).order_by(Product.product_id))
            for product in result.scalars():
                data = {
                    "product_id": product.product_id,
                    "category_id": product.category_id,
                    "name": product.name,
                    "description": product.description,
                    "image_url": product.image_url,
                    "base_price": product.base_price,
                    "status": product.status,
                    "inventory_status": product.inventory_status,
                    "stock_quantity": product.stock_quantity,
                    "created_at": product.created_at,
                    "updated_at": product.updated_at,
                }
                f.write(generate_insert("products", data) + "\n")
            f.write("\n")
            
            # 商品分类关联
            print("  导出商品分类关联...")
            f.write("-- 商品分类关联\n")
            result = await session.execute(select(ProductCategory))
            for pc in result.scalars():
                data = {
                    "product_id": pc.product_id,
                    "category_id": pc.category_id,
                }
                f.write(generate_insert("product_categories", data) + "\n")
            f.write("\n")
            
            # 规格组
            print("  导出规格组...")
            f.write("-- 规格组\n")
            result = await session.execute(select(SpecGroup).order_by(SpecGroup.group_id))
            for group in result.scalars():
                data = {
                    "group_id": group.group_id,
                    "name": group.name,
                    "sort_order": group.sort_order,
                    "created_at": group.created_at,
                }
                f.write(generate_insert("spec_groups", data) + "\n")
            f.write("\n")
            
            # 规格选项
            print("  导出规格选项...")
            f.write("-- 规格选项\n")
            result = await session.execute(select(SpecOption).order_by(SpecOption.option_id))
            for option in result.scalars():
                data = {
                    "option_id": option.option_id,
                    "group_id": option.group_id,
                    "name": option.name,
                    "price_modifier": option.price_modifier,
                    "inventory_status": option.inventory_status,
                    "sort_order": option.sort_order,
                    "created_at": option.created_at,
                }
                f.write(generate_insert("spec_options", data) + "\n")
            f.write("\n")
            
            # 商品规格映射
            print("  导出商品规格映射...")
            f.write("-- 商品规格映射\n")
            result = await session.execute(select(ProductSpecMapping).order_by(ProductSpecMapping.mapping_id))
            for mapping in result.scalars():
                data = {
                    "mapping_id": mapping.mapping_id,
                    "product_id": mapping.product_id,
                    "group_id": mapping.group_id,
                }
                f.write(generate_insert("product_spec_mappings", data) + "\n")
            f.write("\n")
            
            # 店铺设置
            print("  导出店铺设置...")
            f.write("-- 店铺设置\n")
            result = await session.execute(select(ShopSetting).order_by(ShopSetting.key))
            for setting in result.scalars():
                data = {
                    "key": setting.key,
                    "value": setting.value,
                    "description": setting.description,
                }
                f.write(generate_insert("shop_settings", data) + "\n")
            f.write("\n")
            
            # 店铺档案
            print("  导出店铺档案...")
            f.write("-- 店铺档案\n")
            result = await session.execute(select(ShopProfile))
            for profile in result.scalars():
                data = {
                    "id": profile.id,
                    "is_open": profile.is_open,
                    "open_hours_json": profile.open_hours_json,
                    "location_lat": profile.location_lat,
                    "location_lng": profile.location_lng,
                    "delivery_radius_m": profile.delivery_radius_m,
                    "timezone": profile.timezone,
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at,
                }
                f.write(generate_insert("shop_profile", data) + "\n")
            f.write("\n")
            
            # 预约时段
            print("  导出预约时段...")
            f.write("-- 预约时段\n")
            result = await session.execute(select(ReservationSlot).order_by(ReservationSlot.slot_id))
            for slot in result.scalars():
                data = {
                    "slot_id": slot.slot_id,
                    "slot_start": slot.slot_start,
                    "slot_end": slot.slot_end,
                    "capacity": slot.capacity,
                    "reserved_count": slot.reserved_count,
                    "created_at": slot.created_at,
                    "updated_at": slot.updated_at,
                }
                f.write(generate_insert("reservation_slots", data) + "\n")
            f.write("\n")
            
            # 订单
            print("  导出订单...")
            f.write("-- 订单\n")
            result = await session.execute(select(Order).order_by(Order.order_id))
            for order in result.scalars():
                data = {
                    "order_id": order.order_id,
                    "order_number": order.order_number,
                    "user_id": order.user_id,
                    "guest_session_id": order.guest_session_id,
                    "total_price": order.total_price,
                    "notes": order.notes,
                    "status": order.status,
                    "order_type": order.order_type,
                    "address_json": order.address_json,
                    "payment_channel": order.payment_channel,
                    "payment_status": order.payment_status,
                    "source": order.source,
                    "created_by_admin_id": order.created_by_admin_id,
                    "is_scheduled": order.is_scheduled,
                    "scheduled_at": order.scheduled_at,
                    "reminder_sent_at": order.reminder_sent_at,
                    "reservation_slot_id": order.reservation_slot_id,
                    "created_at": order.created_at,
                    "updated_at": order.updated_at,
                }
                f.write(generate_insert("orders", data) + "\n")
            f.write("\n")
            
            # 订单项
            print("  导出订单项...")
            f.write("-- 订单项\n")
            result = await session.execute(select(OrderItem).order_by(OrderItem.item_id))
            for item in result.scalars():
                data = {
                    "item_id": item.item_id,
                    "order_id": item.order_id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "selected_specs_json": item.selected_specs_json,
                }
                f.write(generate_insert("order_items", data) + "\n")
            f.write("\n")
            
            # 支付记录
            print("  导出支付记录...")
            f.write("-- 支付记录\n")
            result = await session.execute(select(PaymentRecord).order_by(PaymentRecord.pay_id))
            for payment in result.scalars():
                data = {
                    "pay_id": payment.pay_id,
                    "record_type": payment.record_type,
                    "channel": payment.channel,
                    "currency": payment.currency,
                    "amount": payment.amount,
                    "txn_id": payment.txn_id,
                    "out_trade_no": payment.out_trade_no,
                    "qr_session_id": payment.qr_session_id,
                    "matched_order_id": payment.matched_order_id,
                    "match_status": payment.match_status,
                    "matched_by_admin_id": payment.matched_by_admin_id,
                    "match_confidence": payment.match_confidence,
                    "paid_at": payment.paid_at,
                    "raw_notification_json": payment.raw_notification_json,
                    "created_at": payment.created_at,
                }
                f.write(generate_insert("payment_records", data) + "\n")
            f.write("\n")
            
            # 优惠券
            print("  导出优惠券...")
            f.write("-- 优惠券\n")
            result = await session.execute(select(Coupon).order_by(Coupon.coupon_id))
            for coupon in result.scalars():
                data = {
                    "coupon_id": coupon.coupon_id,
                    "user_id": coupon.user_id,
                    "type": coupon.type,
                    "status": coupon.status,
                    "meta_json": coupon.meta_json,
                    "issued_at": coupon.issued_at,
                    "used_at": coupon.used_at,
                    "used_in_order_id": coupon.used_in_order_id,
                    "created_at": coupon.created_at,
                }
                f.write(generate_insert("coupons", data) + "\n")
            f.write("\n")
            
            # 积分记录
            print("  导出积分记录...")
            f.write("-- 积分记录\n")
            result = await session.execute(select(LoyaltyTransaction).order_by(LoyaltyTransaction.id))
            for trans in result.scalars():
                data = {
                    "id": trans.id,
                    "user_id": trans.user_id,
                    "order_id": trans.order_id,
                    "delta_points": trans.delta_points,
                    "reason": trans.reason,
                    "created_at": trans.created_at,
                }
                f.write(generate_insert("loyalty_transactions", data) + "\n")
            f.write("\n")
        
        f.write("COMMIT;\n")
    
    await engine.dispose()
    
    print()
    print(f"✅ 数据已导出到: {output_file}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(description="导出测试数据到 SQL 文件")
    parser.add_argument(
        "--output",
        "-o",
        default="test_data.sql",
        help="输出文件路径 (默认: test_data.sql)"
    )
    args = parser.parse_args()
    
    try:
        print("=" * 70)
        print("📤 导出测试数据")
        print("=" * 70)
        print()
        
        await export_data(args.output)
        
        print("💡 使用方法:")
        print(f"   psql -U postgres -d naicha < {args.output}")
        print("   或")
        print(f"   mysql -u root -p naicha < {args.output}")
        print()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
