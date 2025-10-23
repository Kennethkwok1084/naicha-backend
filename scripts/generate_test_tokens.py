#!/usr/bin/env python3
"""
生成用于压测的测试 Token

用法：
    python scripts/generate_test_tokens.py

环境变量（可选）：
    SECRET_KEY: JWT 密钥（默认从 .env 读取或使用默认值）
    ADMIN_ID: 管理员 ID（默认 1）
    USER_ID: 用户 ID（默认 1）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.security import TokenScope, create_access_token
from app.core.settings import get_settings


def main() -> None:
    # 尝试加载设置（会读取 .env）
    try:
        settings = get_settings()
        secret_key = settings.secret_key
    except Exception:
        # 如果无法加载设置，使用默认值
        secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
        print(f"⚠️  警告：使用默认或环境变量中的 SECRET_KEY")

    admin_id = os.getenv("ADMIN_ID", "1")
    user_id = os.getenv("USER_ID", "1")

    print("=" * 70)
    print("🔑 生成压测 Token")
    print("=" * 70)
    print()

    # 生成管理员 Token
    admin_token = create_access_token(subject=admin_id, scope=TokenScope.ADMIN)
    print(f"📋 管理员 Token (ADMIN_ID={admin_id}):")
    print(f"   {admin_token}")
    print()
    print(f"📋 用于环境变量:")
    print(f'   export PERF_ADMIN_TOKEN="Bearer {admin_token}"')
    print()

    # 生成用户 Token
    user_token = create_access_token(subject=user_id, scope=TokenScope.USER)
    print(f"📋 用户 Token (USER_ID={user_id}):")
    print(f"   {user_token}")
    print()
    print(f"📋 用于环境变量:")
    print(f'   export PERF_USER_TOKEN="Bearer {user_token}"')
    print()

    print("=" * 70)
    print("✅ 完成！复制上面的 export 命令即可使用")
    print("=" * 70)
    print()
    print("💡 提示：")
    print("   - 这些 Token 用于开发/测试环境，不要在生产环境使用")
    print("   - Token 过期时间由 JWT_EXPIRE_MINUTES 控制（默认 43200 分钟 = 30 天）")
    print("   - 如需自定义 ID，使用环境变量：")
    print("     ADMIN_ID=2 USER_ID=3 python scripts/generate_test_tokens.py")
    print()


if __name__ == "__main__":
    main()
