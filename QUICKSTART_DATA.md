# 快速开始 - 测试数据

## 一键填充测试数据

```bash
# 1. 确保数据库已创建表结构
make updb

# 2. 填充测试数据
make seed-data

# 3. 验证数据
python scripts/verify_test_data.py
```

## 常用命令

```bash
# 创建测试数据（保留现有数据）
make seed-data

# 清空并重新创建测试数据
make seed-clean

# 创建开发环境管理员
export NAICHA_DEV_ADMIN_HASH='$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq'
make seed-dev

# 创建性能测试数据
make seed-perf

# 验证数据完整性
python scripts/verify_test_data.py

# 导出数据到 SQL 文件
python scripts/export_test_data.py
python scripts/export_test_data.py --output backup.sql
```

## 测试账号

### 管理员
- **用户名**: admin / **密码**: admin123 (角色: admin)
- **用户名**: manager / **密码**: admin123 (角色: manager)  
- **用户名**: clerk / **密码**: admin123 (角色: clerk)

### 普通用户
- **张三** (user_id: 1, open_id: test_openid_001, 积分: 100)
- **李四** (user_id: 2, open_id: test_openid_002, 积分: 250)
- **王五** (user_id: 3, open_id: test_openid_003, 积分: 50)
- **赵六** (user_id: 4, open_id: test_openid_004, 积分: 0)

## API 测试示例

启动服务器后，可以测试以下 API：

```bash
# 获取菜单
curl http://localhost:8000/api/menu

# 获取商品详情
curl http://localhost:8000/api/products/1

# 获取商品分类
curl http://localhost:8000/api/categories

# 获取店铺信息
curl http://localhost:8000/api/shop/profile

# 查看订单列表（需要认证）
curl http://localhost:8000/api/orders?user_id=1
```

## 数据概览

填充的测试数据包括：

| 数据类型 | 数量 | 说明 |
|---------|------|------|
| 管理员 | 3 | admin, manager, clerk |
| 用户 | 4 | 包含地址和积分 |
| 商品分类 | 5 | 奶茶、果茶、咖啡、甜品、季节限定 |
| 商品 | 10 | 不同价格和状态 |
| 规格组 | 4 | 糖度、冰度、杯型、加料 |
| 规格选项 | 17 | 各规格的详细选项 |
| 订单 | 8 | 覆盖所有状态 |
| 支付记录 | 6 | 不同支付渠道 |
| 优惠券 | 5 | 不同状态 |
| 预约时段 | 35 | 未来7天 |

## 故障排除

### 错误: 表不存在
```bash
# 运行数据库迁移
make updb
```

### 错误: 主键冲突
```bash
# 使用 --clean 清空数据
make seed-clean
```

### 错误: 数据库连接失败
```bash
# 检查 .env 文件或环境变量
cat .env | grep DATABASE_URL

# 确保数据库服务运行
docker ps | grep postgres
```

## 详细文档

查看 [scripts/README.md](scripts/README.md) 了解更多详情。
