# 测试数据填充脚本使用指南

## 概述

本目录包含用于创建测试数据的脚本，可用于前端开发和后端测试。

## 脚本说明

### 1. seed_test_data.py - 完整测试数据填充

创建包含所有业务场景的完整测试数据，包括：

- **管理员账号** (3个): admin, manager, clerk
- **测试用户** (4个): 张三、李四、王五、赵六
- **用户地址** (4个): 不同城市的配送地址
- **商品分类** (5个): 奶茶、果茶、咖啡、甜品、季节限定
- **商品** (10个): 包含不同价格、状态和库存的商品
- **规格** (4组): 糖度、冰度、杯型、加料及相应选项
- **订单** (8个): 覆盖所有订单状态
- **支付记录** (6条): 不同支付渠道和匹配状态
- **优惠券** (5张): 不同状态的优惠券
- **积分记录** (9条): 订单积分、优惠券积分等
- **预约时段** (35个): 未来7天的时段

### 2. seed_dev.py - 开发环境管理员

仅创建一个管理员账号，用于开发环境快速启动。

### 3. seed_perf_data.py - 性能测试数据

创建精简的压测数据，用于性能测试。

## 使用方法

### 前置条件

1. 确保数据库正在运行
2. 已设置好数据库连接（`.env` 文件或环境变量 `DATABASE_URL`）
3. 已运行数据库迁移：`alembic upgrade head`

### 创建完整测试数据

```bash
# 激活虚拟环境
source .venv/bin/activate

# 创建测试数据（保留现有数据）
python scripts/seed_test_data.py

# 清空现有数据后重新创建
python scripts/seed_test_data.py --clean
```

### 创建管理员账号

```bash
# 需要先设置环境变量
export NAICHA_DEV_ADMIN_USERNAME=admin
export NAICHA_DEV_ADMIN_HASH='$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq'

python scripts/seed_dev.py
```

### 创建性能测试数据

```bash
python scripts/seed_perf_data.py
```

## 测试账号

### 管理员账号

| 用户名 | 密码 | 角色 | ID |
|--------|------|------|-----|
| admin | admin123 | admin | 1 |
| manager | admin123 | manager | 2 |
| clerk | admin123 | clerk | 3 |

### 测试用户

| 用户ID | 昵称 | OpenID | 积分 |
|--------|------|--------|------|
| 1 | 张三 | test_openid_001 | 100 |
| 2 | 李四 | test_openid_002 | 250 |
| 3 | 王五 | test_openid_003 | 50 |
| 4 | 赵六 | test_openid_004 | 0 |

## 数据详情

### 商品列表

| ID | 名称 | 分类 | 价格 | 状态 | 库存状态 |
|----|------|------|------|------|----------|
| 1 | 珍珠奶茶 | 奶茶系列 | ¥15.00 | active | in_stock |
| 2 | 波霸奶茶 | 奶茶系列 | ¥16.00 | active | in_stock |
| 3 | 布丁奶茶 | 奶茶系列 | ¥17.00 | active | in_stock |
| 4 | 水果茶 | 果茶系列 | ¥18.00 | active | in_stock |
| 5 | 柠檬茶 | 果茶系列 | ¥14.00 | active | in_stock |
| 6 | 芒果冰沙 | 果茶系列/季节限定 | ¥20.00 | active | sold_out |
| 7 | 美式咖啡 | 咖啡系列 | ¥16.00 | active | in_stock |
| 8 | 拿铁咖啡 | 咖啡系列 | ¥18.00 | active | in_stock |
| 9 | 摩卡咖啡 | 咖啡系列 | ¥19.00 | inactive | in_stock |
| 10 | 芝士蛋糕 | 甜品系列 | ¥25.00 | active | in_stock |

### 规格配置

#### 糖度选项
- 正常糖、七分糖、半糖、三分糖、无糖

#### 冰度选项
- 正常冰、少冰、去冰、热饮

#### 杯型选项
- 中杯 (+¥0)
- 大杯 (+¥3)
- 超大杯 (+¥5)

#### 加料选项
- 珍珠 (+¥2)
- 椰果 (+¥2)
- 布丁 (+¥3)
- 仙草 (+¥2, 已售罄)
- 芋圆 (+¥3)

### 订单示例

| 订单号 | 用户 | 状态 | 类型 | 总价 | 说明 |
|--------|------|------|------|------|------|
| ON20231001001 | 张三 | paid | pickup | ¥35.00 | 已支付待制作 |
| ON20231001002 | 李四 | in_production | delivery | ¥52.00 | 制作中 |
| ON20231001003 | 张三 | ready_for_pickup | pickup | ¥18.00 | 待取货 |
| ON20231001004 | 王五 | completed | delivery | ¥44.00 | 已完成 |
| ON20231001005 | 张三 | pending_payment | pickup | ¥25.00 | 待支付 |
| ON20231001006 | 李四 | cancelled | pickup | ¥30.00 | 已取消 |
| ON20231001007 | - | completed | pickup | ¥40.00 | POS订单 |
| ON20231001008 | 王五 | paid | pickup | ¥60.00 | 预约订单 |

### 店铺配置

- 店铺名称: 奶茶小站
- 营业时间: 周一至周四 9:00-22:00，周五周六 9:00-23:00，周日 10:00-22:00
- 配送范围: 5000米
- 最低配送金额: ¥20.00
- 配送费: ¥5.00
- 免配送费金额: ¥50.00

## API 测试示例

### 获取菜单

```bash
curl http://localhost:8000/api/menu
```

### 用户登录（需要根据你的实际API调整）

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"open_id": "test_openid_001"}'
```

### 创建订单

```bash
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "order_type": "pickup",
    "items": [
      {
        "product_id": 1,
        "quantity": 1,
        "selected_specs": {
          "糖度": "半糖",
          "冰度": "少冰",
          "杯型": "大杯"
        }
      }
    ]
  }'
```

### 获取用户订单

```bash
curl http://localhost:8000/api/orders?user_id=1
```

## 数据重置

如果需要完全重置数据：

```bash
# 方法1: 使用 --clean 参数
python scripts/seed_test_data.py --clean

# 方法2: 手动重置数据库
alembic downgrade base
alembic upgrade head
python scripts/seed_test_data.py
```

## 故障排除

### 错误: 数据库连接失败

检查：
1. 数据库服务是否运行
2. `.env` 文件中的 `DATABASE_URL` 是否正确
3. 数据库用户权限是否足够

### 错误: 表不存在

运行数据库迁移：
```bash
alembic upgrade head
```

### 错误: 主键冲突

数据已存在，使用 `--clean` 参数清空后重新创建：
```bash
python scripts/seed_test_data.py --clean
```

## 扩展数据

如果需要添加更多测试数据，可以：

1. 直接修改 `seed_test_data.py` 中的数据数组
2. 创建自己的填充脚本
3. 使用数据库管理工具手动添加

## 注意事项

1. **不要在生产环境运行这些脚本**，仅用于开发和测试
2. 使用 `--clean` 参数会删除所有现有数据，请谨慎使用
3. 管理员密码使用 bcrypt 加密，默认密码为 `admin123`
4. 测试用户的 `open_id` 是模拟的，实际使用时需要从微信获取
5. 支付记录中的交易ID是模拟的，不能用于真实支付

## 相关文档

- [开发指南](../doc/develop.md)
- [API 文档](../doc/api.md)
- [部署指南](../doc/deployment-guide-v3.0.1.md)
