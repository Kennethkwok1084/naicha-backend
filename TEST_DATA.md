# 测试数据填充系统

## 📦 已创建的文件

### 核心脚本

1. **`scripts/seed_test_data.py`** - 主要的测试数据填充脚本
   - 创建完整的测试数据集
   - 支持 `--clean` 参数清空现有数据
   - 包含所有业务场景的数据

2. **`scripts/verify_test_data.py`** - 数据验证脚本
   - 检查数据完整性
   - 显示数据统计和详细信息
   - 帮助排查数据问题

3. **`scripts/export_test_data.py`** - 数据导出脚本
   - 导出数据到 SQL 文件
   - 便于备份和分享
   - 支持自定义输出路径

### 文档

1. **`scripts/README.md`** - 脚本详细使用文档
   - 所有脚本的使用说明
   - 测试账号信息
   - 数据详情表格
   - 故障排除指南

2. **`QUICKSTART_DATA.md`** - 快速开始指南
   - 一键命令速查
   - 常用操作示例
   - 快速故障排除

3. **`doc/test-data-demo.md`** - 完整演示文档
   - 从零开始的完整流程
   - 前端开发使用场景
   - 后端测试使用场景
   - 最佳实践建议

### Makefile 集成

新增的 Make 目标：

```makefile
make seed-data    # 创建测试数据
make seed-clean   # 清空并重新创建
make seed-dev     # 创建管理员账号
make seed-perf    # 创建性能测试数据
```

## 🎯 主要功能

### 测试数据内容

| 类型 | 数量 | 说明 |
|------|------|------|
| 👤 管理员 | 3 | admin, manager, clerk (密码: admin123) |
| 👥 用户 | 4 | 张三、李四、王五、赵六，包含积分和偏好 |
| 📍 地址 | 4 | 不同城市的配送地址 |
| 📂 分类 | 5 | 奶茶、果茶、咖啡、甜品、季节限定 |
| 🥤 商品 | 10 | 不同价格、状态和库存的商品 |
| 🎨 规格组 | 4 | 糖度、冰度、杯型、加料 |
| ⚙️ 规格选项 | 17 | 各规格的详细选项 |
| 📦 订单 | 8 | 覆盖所有订单状态 (待支付/已支付/制作中/待取货/已完成/已取消/POS订单/预约订单) |
| 📝 订单项 | 12 | 订单中的商品详情 |
| 💰 支付记录 | 6 | 不同支付渠道和匹配状态 |
| 🎫 优惠券 | 5 | 不同状态 (可用/已使用/已过期) |
| ⭐ 积分记录 | 9 | 订单积分、优惠券积分等 |
| 📅 预约时段 | 35 | 未来7天的预约时段 |
| ⚙️ 店铺设置 | 6 | 店名、电话、地址、配送费等 |
| 🏪 店铺档案 | 1 | 营业时间、位置、配送范围等 |

### 数据特点

✅ **真实场景** - 包含各种业务状态和边界情况  
✅ **即用即测** - 数据之间关联完整，可直接测试  
✅ **中文友好** - 使用中文名称和地址  
✅ **可重置** - 支持快速清空和重建  
✅ **可验证** - 提供验证工具检查完整性  
✅ **可导出** - 支持导出为 SQL 文件  

## 🚀 快速开始

### 1. 首次使用

```bash
# 1. 创建数据库表
make updb

# 2. 填充测试数据
make seed-data

# 3. 验证数据
python scripts/verify_test_data.py

# 4. 启动服务
make dev
```

### 2. 日常使用

```bash
# 重置测试数据
make seed-clean

# 验证数据
python scripts/verify_test_data.py

# 导出备份
python scripts/export_test_data.py --output backup.sql
```

## 📱 使用场景

### 前端开发

```javascript
// 获取菜单 - 包含10个商品
fetch('http://localhost:8000/api/menu')

// 获取用户信息 - 张三(user_id=1)，有100积分
fetch('http://localhost:8000/api/users/1')

// 获取订单列表 - 张三有4个不同状态的订单
fetch('http://localhost:8000/api/orders?user_id=1')

// 获取优惠券 - 李四(user_id=2)有2张可用优惠券
fetch('http://localhost:8000/api/coupons?user_id=2&status=active')
```

### 后端测试

```python
# 单元测试 - 使用测试用户
@pytest.mark.asyncio
async def test_user_orders(db_session):
    result = await db_session.execute(
        select(Order).where(Order.user_id == 1)
    )
    orders = result.scalars().all()
    assert len(orders) >= 3  # 张三有多个订单

# 集成测试 - 测试完整流程
async def test_order_flow(client):
    response = await client.post("/api/orders", json={
        "user_id": 1,
        "items": [{"product_id": 1, "quantity": 1}]
    })
    assert response.status_code == 201
```

### API 测试

```bash
# 测试菜单接口
curl http://localhost:8000/api/menu | jq

# 测试商品详情
curl http://localhost:8000/api/products/1 | jq

# 测试订单查询
curl http://localhost:8000/api/orders?user_id=1 | jq

# 测试店铺信息
curl http://localhost:8000/api/shop/profile | jq
```

## 🔐 测试账号

### 管理员账号

| 用户名 | 密码 | 角色 | 用途 |
|--------|------|------|------|
| admin | admin123 | admin | 超级管理员 |
| manager | admin123 | manager | 店长 |
| clerk | admin123 | clerk | 店员 |

### 测试用户

| 用户ID | 昵称 | OpenID | 积分 | 地址数 | 订单数 | 优惠券 |
|--------|------|--------|------|--------|--------|--------|
| 1 | 张三 | test_openid_001 | 100 | 2 | 4 | 1可用+1已用 |
| 2 | 李四 | test_openid_002 | 250 | 1 | 2 | 2可用 |
| 3 | 王五 | test_openid_003 | 50 | 1 | 2 | 1已过期 |
| 4 | 赵六 | test_openid_004 | 0 | 0 | 0 | 0 |

## 📊 数据关系

```
用户 (Users)
  ├─ 地址 (UserAddress)
  ├─ 订单 (Orders)
  │   └─ 订单项 (OrderItems) → 商品 (Products)
  ├─ 优惠券 (Coupons)
  └─ 积分记录 (LoyaltyTransaction)

商品 (Products)
  ├─ 分类 (Categories)
  └─ 规格映射 (ProductSpecMapping)
      └─ 规格组 (SpecGroups)
          └─ 规格选项 (SpecOptions)

订单 (Orders)
  ├─ 支付记录 (PaymentRecords)
  └─ 预约时段 (ReservationSlots)

店铺 (Shop)
  ├─ 店铺设置 (ShopSettings)
  └─ 店铺档案 (ShopProfile)
```

## 🛠️ 维护和扩展

### 添加新数据

编辑 `scripts/seed_test_data.py`，在相应函数中添加数据：

```python
async def seed_products(session_factory) -> None:
    # 添加新商品
    products_data = [
        # ... 现有数据
        {
            "product_id": 11,
            "name": "新商品",
            "base_price": Decimal("20.00"),
            # ...
        }
    ]
```

### 创建自定义脚本

```python
# scripts/seed_custom.py
from scripts.seed_test_data import *

async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(bind=engine)
    
    # 只创建需要的数据
    await seed_users(session_factory)
    await seed_products(session_factory)
    
    await engine.dispose()
```

## ⚠️ 注意事项

1. **仅用于开发和测试** - 不要在生产环境运行
2. **数据库隔离** - 使用独立的测试数据库
3. **定期重置** - 避免脏数据影响测试
4. **版本控制** - 脚本纳入 Git 管理
5. **密码安全** - 测试密码仅用于开发环境

## 📚 相关文档

- [详细使用文档](scripts/README.md)
- [快速开始指南](QUICKSTART_DATA.md)
- [完整演示](doc/test-data-demo.md)
- [开发指南](doc/develop.md)
- [API 文档](doc/api.md)

## 🤝 贡献

如果你添加了有用的测试数据或改进了脚本，欢迎提交 PR！

## 📝 更新日志

### 2024-10-26

- ✅ 创建完整的测试数据填充系统
- ✅ 添加数据验证脚本
- ✅ 添加数据导出功能
- ✅ 集成到 Makefile
- ✅ 编写详细文档

---

**祝开发顺利！** 🎉
