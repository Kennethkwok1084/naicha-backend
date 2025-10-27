# 测试数据使用演示

## 完整流程示例

以下是从零开始设置测试数据的完整流程：

### 1. 准备数据库

```bash
# 方式A: 使用 Docker Compose（推荐）
docker-compose up -d postgres

# 方式B: 使用已有的 PostgreSQL 服务
# 确保 .env 文件中配置了正确的 DATABASE_URL
```

### 2. 创建数据库表结构

```bash
# 运行数据库迁移
alembic upgrade head

# 或使用 Makefile
make updb
```

### 3. 填充测试数据

```bash
# 方式A: 使用 Makefile（推荐）
make seed-data

# 方式B: 直接运行 Python 脚本
python scripts/seed_test_data.py

# 方式C: 清空现有数据后填充
make seed-clean
# 或
python scripts/seed_test_data.py --clean
```

### 4. 验证数据

```bash
python scripts/verify_test_data.py
```

成功后会看到类似输出：

```
======================================================================
🔍 验证测试数据
======================================================================

✅ 管理员        :   3 条 (预期 >= 3)
✅ 用户          :   4 条 (预期 >= 4)
✅ 用户地址      :   4 条 (预期 >= 4)
✅ 商品分类      :   5 条 (预期 >= 5)
✅ 商品          :  10 条 (预期 >= 10)
✅ 规格组        :   4 条 (预期 >= 4)
✅ 规格选项      :  17 条 (预期 >= 17)
✅ 订单          :   8 条 (预期 >= 8)
✅ 订单项        :  12 条 (预期 >= 12)
✅ 支付记录      :   6 条 (预期 >= 6)
✅ 优惠券        :   5 条 (预期 >= 5)
✅ 积分记录      :   9 条 (预期 >= 9)
✅ 预约时段      :  35 条 (预期 >= 35)
✅ 店铺设置      :   6 条 (预期 >= 6)
✅ 店铺档案      :   1 条 (预期 >= 1)

📋 详细检查:

👤 管理员账号:
   - admin (admin)
   - manager (manager)
   - clerk (clerk)

👥 测试用户:
   - 张三 (积分: 100)
   - 李四 (积分: 250)
   - 王五 (积分: 50)
   - 赵六 (积分: 0)

🥤 商品列表:
   ✓ 📦 珍珠奶茶       - ¥15.00
   ✓ 📦 波霸奶茶       - ¥16.00
   ✓ 📦 布丁奶茶       - ¥17.00
   ✓ 📦 水果茶        - ¥18.00
   ✓ 📦 柠檬茶        - ¥14.00
   ✓ ❌ 芒果冰沙       - ¥20.00
   ✓ 📦 美式咖啡       - ¥16.00
   ✓ 📦 拿铁咖啡       - ¥18.00
   ⊗ 📦 摩卡咖啡       - ¥19.00
   ✓ 📦 芝士蛋糕       - ¥25.00

...
```

### 5. 启动后端服务

```bash
# 开发模式
make dev

# 或直接使用 uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 测试 API

```bash
# 获取菜单
curl http://localhost:8000/api/menu | jq

# 获取所有分类
curl http://localhost:8000/api/categories | jq

# 获取特定商品
curl http://localhost:8000/api/products/1 | jq

# 获取店铺信息
curl http://localhost:8000/api/shop/profile | jq

# 查看用户订单（需要认证）
curl http://localhost:8000/api/orders?user_id=1 | jq
```

## 前端开发使用场景

### 场景 1: 测试商品列表页

```javascript
// 获取所有商品
fetch('http://localhost:8000/api/menu')
  .then(res => res.json())
  .then(data => {
    console.log('商品数据:', data);
    // data 包含 10 个测试商品
  });
```

### 场景 2: 测试订单流程

1. **创建订单** - 使用 user_id=1 (张三)
2. **支付订单** - 测试支付回调
3. **查看订单** - 获取订单列表和详情
4. **取消订单** - 测试取消逻辑

### 场景 3: 测试用户中心

```javascript
// 获取用户信息 (张三)
const userId = 1;
fetch(`http://localhost:8000/api/users/${userId}`)
  .then(res => res.json())
  .then(user => {
    console.log('用户信息:', user);
    console.log('积分:', user.loyalty_points); // 100
    console.log('地址数:', user.addresses.length); // 2
  });
```

### 场景 4: 测试优惠券系统

```javascript
// 获取用户优惠券 (李四有2张可用优惠券)
const userId = 2;
fetch(`http://localhost:8000/api/coupons?user_id=${userId}&status=active`)
  .then(res => res.json())
  .then(coupons => {
    console.log('可用优惠券:', coupons); // 2 张
  });
```

### 场景 5: 测试预约功能

```javascript
// 获取未来的预约时段
fetch('http://localhost:8000/api/reservation-slots?available=true')
  .then(res => res.json())
  .then(slots => {
    console.log('可用时段:', slots); // 35 个时段
  });
```

## 后端测试使用场景

### 场景 1: 单元测试

```python
# tests/test_orders.py
import pytest
from app.models.orders import Order
from sqlalchemy import select

@pytest.mark.asyncio
async def test_get_user_orders(db_session):
    # 使用测试数据中的用户1（张三）
    result = await db_session.execute(
        select(Order).where(Order.user_id == 1)
    )
    orders = result.scalars().all()
    
    # 张三有4个订单
    assert len(orders) >= 3
```

### 场景 2: 集成测试

```python
# tests/integration/test_order_flow.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_complete_order_flow(client: AsyncClient):
    # 1. 获取菜单
    response = await client.get("/api/menu")
    assert response.status_code == 200
    products = response.json()
    assert len(products) >= 10
    
    # 2. 创建订单（使用测试用户1）
    order_data = {
        "user_id": 1,
        "items": [
            {"product_id": 1, "quantity": 1}
        ]
    }
    response = await client.post("/api/orders", json=order_data)
    assert response.status_code == 201
```

### 场景 3: 性能测试

```python
# 使用测试数据进行压测
# infra/perf/locustfile.py

class UserBehavior(User):
    @task
    def view_menu(self):
        # 菜单中有10个商品
        self.client.get("/api/menu")
    
    @task
    def view_product(self):
        # 随机查看商品 1-10
        product_id = random.randint(1, 10)
        self.client.get(f"/api/products/{product_id}")
```

## 数据重置

开发过程中如果数据被污染，可以快速重置：

```bash
# 方式1: 使用 Makefile（推荐）
make seed-clean

# 方式2: 手动清理
alembic downgrade base
alembic upgrade head
python scripts/seed_test_data.py
```

## 数据备份与恢复

### 导出数据

```bash
# 导出到 SQL 文件
python scripts/export_test_data.py --output backup.sql

# 或导出整个数据库
pg_dump -U postgres naicha > backup_full.sql
```

### 恢复数据

```bash
# 从 SQL 文件恢复
psql -U postgres naicha < backup.sql

# 或从完整备份恢复
psql -U postgres naicha < backup_full.sql
```

## 常见问题

### Q: 如何添加更多测试数据？

修改 `scripts/seed_test_data.py` 文件中的数据数组，然后运行：

```bash
python scripts/seed_test_data.py --clean
```

### Q: 如何只创建特定类型的数据？

可以注释掉不需要的函数调用，或者创建自定义脚本：

```python
# scripts/seed_custom.py
from scripts.seed_test_data import seed_users, seed_products

async def main():
    # 只创建用户和商品
    await seed_users(session_factory)
    await seed_products(session_factory)
```

### Q: 测试数据会影响生产环境吗？

不会，只要你：
1. ✅ 不在生产数据库上运行这些脚本
2. ✅ 使用不同的 DATABASE_URL
3. ✅ 在 .env 文件中正确配置环境

### Q: 如何验证前端获取的数据是否正确？

1. 使用 `verify_test_data.py` 验证数据库数据
2. 使用浏览器开发者工具查看 API 响应
3. 对比返回的数据与文档中的预期数据

## 最佳实践

1. **定期重置数据**
   - 每天开始开发前运行 `make seed-clean`
   - 确保测试数据的一致性

2. **使用独立的测试数据库**
   - 开发环境使用一个数据库
   - 测试环境使用另一个数据库
   - 生产环境绝不运行测试脚本

3. **文档化自定义数据**
   - 如果添加了自定义测试数据，在代码中添加注释
   - 更新 README 说明新增的测试场景

4. **版本控制**
   - 测试数据脚本纳入版本控制
   - 与团队成员同步测试数据结构

## 相关资源

- [完整文档](scripts/README.md)
- [快速开始](QUICKSTART_DATA.md)
- [API 文档](doc/api.md)
- [开发指南](doc/develop.md)
