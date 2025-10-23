#!/usr/bin/env python3
"""
快速创建测试管理员账号

用法：
    # 创建默认管理员（admin/admin123）
    python scripts/create_test_admin.py

    # 创建自定义管理员
    python scripts/create_test_admin.py --username testadmin --password mypass123

环境变量：
    DATABASE_URL: 数据库连接 URL（默认从 .env 读取）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.security import hash_password
from app.core.settings import get_settings
from app.models.accounts import Admin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def create_admin(username: str, password: str) -> None:
    settings = get_settings()
    password_hash = hash_password(password)

    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        # 检查是否已存在
        result = await session.execute(select(Admin).where(Admin.username == username))
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"⚠️  管理员 '{username}' 已存在")
            print(f"   Admin ID: {existing.admin_id}")
            print(f"   Role: {existing.role}")
            print()
            print("💡 如需重置密码，请使用 SQL 或删除后重新创建：")
            print(f"   DELETE FROM admins WHERE username = '{username}';")
        else:
            new_admin = Admin(username=username, password_hash=password_hash, role="admin")
            session.add(new_admin)
            await session.commit()
            await session.refresh(new_admin)
            
            print(f"✅ 成功创建管理员账号")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
            print(f"   Admin ID: {new_admin.admin_id}")
            print()
            print("🔑 获取 Token:")
            print(f"   ADMIN_ID={new_admin.admin_id} python scripts/generate_test_tokens.py")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="创建测试管理员账号")
    parser.add_argument(
        "--username",
        default="admin",
        help="管理员用户名（默认: admin）"
    )
    parser.add_argument(
        "--password",
        default="admin123",
        help="管理员密码（默认: admin123）"
    )
    
    args = parser.parse_args()

    print("=" * 70)
    print("👤 创建测试管理员账号")
    print("=" * 70)
    print()
    
    try:
        asyncio.run(create_admin(args.username, args.password))
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
