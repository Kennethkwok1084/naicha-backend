# 上线前验证完整指南

**版本**: V1.0  
**适用系统**: naicha-backend V3.0.1+  
**最后更新**: 2025-10-27

---

## 📋 目录

1. [验证流程总览](#验证流程总览)
2. [阶段一：本地环境验证](#阶段一本地环境验证)
3. [阶段二：自动化测试](#阶段二自动化测试)
4. [阶段三：Staging 环境验证](#阶段三staging-环境验证)
5. [阶段四：API 接口测试（Apifox/Postman）](#阶段四api-接口测试apifoxpostman)
6. [阶段五：性能压测](#阶段五性能压测)
7. [阶段六：容灾演练](#阶段六容灾演练)
8. [阶段七：生产配置审查](#阶段七生产配置审查)
9. [阶段八：灰度上线](#阶段八灰度上线)
10. [常见问题排查](#常见问题排查)

---

## 验证流程总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        上线验证流程                              │
└─────────────────────────────────────────────────────────────────┘

本地验证 (Day 0-1)
  ├─ 代码质量检查 (make lint)
  ├─ 单元测试 (make test)
  ├─ 测试数据创建 (make seed-data)
  └─ 本地启动验证

API 接口测试 (Day 1-2)
  ├─ 导出 OpenAPI 文档
  ├─ Apifox 导入并生成测试用例
  ├─ 手动测试关键路径
  └─ 自动化回归测试集

Staging 环境验证 (Day 2-3)
  ├─ 部署到 Staging
  ├─ 数据库迁移验证
  ├─ 功能冒烟测试
  └─ 集成测试

性能压测 (Day 3-4)
  ├─ 50 并发基线测试
  ├─ 100 并发压力测试
  ├─ 150 并发极限测试
  └─ 性能指标收集

容灾演练 (Day 4)
  ├─ Redis 故障演练
  ├─ 数据库连接池耗尽模拟
  ├─ 依赖服务降级验证
  └─ 快速回滚演练

生产配置审查 (Day 5)
  ├─ 环境变量检查
  ├─ 安全配置审核
  ├─ 监控告警配置
  └─ 备份策略确认

灰度上线 (Day 6-8)
  ├─ 10% 流量灰度
  ├─ 50% 流量扩大
  ├─ 100% 全量上线
  └─ 持续监控 72 小时
```

---

## 阶段一：本地环境验证

### 1.1 环境准备

```bash
# 1. 克隆代码并切换到目标分支
git clone <repo_url>
cd naicha-backend
git checkout master  # 或待上线的分支

# 2. 创建 Python 虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖
make install
make install-dev

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置：
# - DATABASE_URL
# - SECRET_KEY (使用 openssl rand -hex 32 生成)
# - JWT_SECRET_KEY (同上)
```

### 1.2 代码质量检查

```bash
# 代码格式化
make fmt

# 静态代码检查
make lint

# 预期结果：
# ✅ 0 errors, 0 warnings (中文字符警告可忽略)
```

### 1.3 数据库初始化

```bash
# 启动 PostgreSQL (Docker)
docker run -d \
  --name naicha-postgres \
  -e POSTGRES_USER=naicha \
  -e POSTGRES_PASSWORD=naicha123 \
  -e POSTGRES_DB=naicha \
  -p 5432:5432 \
  postgres:15-alpine

# 执行数据库迁移
make updb

# 预期输出：
# INFO  [alembic.runtime.migration] Running upgrade  -> 20251024_0001
# INFO  [alembic.runtime.migration] Running upgrade 20251024_0001 -> 20251024_0002
```

### 1.4 创建测试数据

```bash
# 创建完整测试数据集
make seed-data

# 预期输出：
# ✅ 创建了 3 个管理员账号
# ✅ 创建了 4 个用户账号
# ✅ 创建了 10 个商品
# ✅ 创建了 8 个订单
# 详见 TEST_DATA.md
```

### 1.5 启动本地服务

```bash
# 终端 1: 启动 API 服务器
make dev

# 终端 2: 启动 Celery Worker (可选)
make worker

# 访问 API 文档
open http://localhost:8000/docs
```

### 1.6 本地冒烟测试

使用浏览器或 curl 快速验证关键接口：

```bash
# 1. 健康检查
curl http://localhost:8000/health
# 预期: {"status": "ok", "version": "3.0.1"}

# 2. 获取菜单
curl http://localhost:8000/api/v1/menu
# 预期: 返回完整菜单 JSON

# 3. 获取门店状态
curl http://localhost:8000/api/v1/shop/status
# 预期: {"is_open": true, "delivery_radius_m": 1500, ...}

# 4. 管理员登录
curl -X POST http://localhost:8000/api/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
# 预期: {"access_token": "eyJ...", "token_type": "bearer"}
```

✅ **验收标准**:
- [ ] 所有接口返回 200 状态码
- [ ] 返回数据结构符合预期
- [ ] 日志无 ERROR 级别输出

---

## 阶段二：自动化测试

### 2.1 单元测试

```bash
# 运行所有测试
make test

# 预期输出：
# ========================= test session starts ==========================
# collected 128 items
# 
# tests/api/test_admin_auth.py ........                           [  6%]
# tests/api/test_orders_routes.py ....................            [ 22%]
# tests/services/test_order_service.py ................           [ 35%]
# ...
# ========================= 128 passed, 5 skipped in 45.67s ==============
```

### 2.2 测试覆盖率

```bash
# 生成覆盖率报告
make coverage

# 查看 HTML 报告
open htmlcov/index.html

# 预期覆盖率：
# - 总体覆盖率: ≥ 70%
# - 核心服务层 (app/services/): ≥ 75%
# - API 路由层 (app/api/): ≥ 65%
```

### 2.3 关键路径测试验证

确保以下关键测试通过：

```bash
# 订单创建并发安全
pytest tests/services/test_order_service.py::test_create_order_concurrent_idempotency -v

# 支付回调幂等性
pytest tests/services/test_payment_service.py::test_payment_callback_duplicate_handling -v

# 库存扣减并发安全
pytest tests/services/test_order_service.py::test_create_order_concurrent_stock_deduction -v

# 静态码支付匹配
pytest tests/api/test_admin_payment_match.py::test_match_payment_unique -v

# 会员积分幂等
pytest tests/services/test_loyalty_service.py::test_award_points_idempotent -v
```

✅ **验收标准**:
- [ ] 所有测试通过
- [ ] 覆盖率达标
- [ ] 无并发竞态条件失败

---

## 阶段三：Staging 环境验证

### 3.1 部署到 Staging

```bash
# 构建 Docker 镜像
docker build -t naicha-backend:staging .

# 推送到镜像仓库
docker tag naicha-backend:staging <registry>/naicha-backend:staging
docker push <registry>/naicha-backend:staging

# 部署到 K8s Staging 命名空间
kubectl apply -f infra/k8s/deployment.yaml -n staging
kubectl apply -f infra/k8s/service.yaml -n staging

# 等待 Pod 就绪
kubectl rollout status deployment/naicha-backend -n staging
```

### 3.2 数据库迁移验证

```bash
# 进入 Pod 执行迁移
kubectl exec -it -n staging deployment/naicha-backend -- alembic upgrade head

# 验证迁移状态
kubectl exec -it -n staging deployment/naicha-backend -- alembic current
# 预期输出: 20251024_0002 (head)

# 验证表结构
kubectl exec -it -n staging deployment/naicha-backend -- \
  psql $DATABASE_URL -c "\dt"
# 检查关键表是否存在: orders, payment_records, print_jobs, audit_logs
```

### 3.3 Staging 环境冒烟测试

```bash
STAGING_URL="https://staging-api.example.com"

# 1. 健康检查
curl $STAGING_URL/health

# 2. 管理员登录
ADMIN_TOKEN=$(curl -X POST $STAGING_URL/api/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<staging_password>"}' \
  | jq -r '.access_token')

# 3. 创建 POS 订单
curl -X POST $STAGING_URL/api/v1/admin/orders \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-$(date +%s)" \
  -d '{
    "items": [{"product_id": 1, "quantity": 1}],
    "payment_channel": "cash"
  }'

# 4. 查看订单列表
curl $STAGING_URL/api/v1/admin/orders?limit=10 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

✅ **验收标准**:
- [ ] Staging 环境可访问
- [ ] 数据库迁移成功
- [ ] 核心 API 功能正常
- [ ] 日志采集正常

---

## 阶段四：API 接口测试（Apifox/Postman）

### 4.1 导出 OpenAPI 文档

#### 方法 1: 从运行中的服务导出

```bash
# 启动本地或 Staging 服务
curl http://localhost:8000/openapi.json > openapi.json

# 或直接从 Staging
curl https://staging-api.example.com/openapi.json > openapi.json
```

#### 方法 2: 从代码生成

```bash
python -c "
from app.main import app
import json

with open('openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2, ensure_ascii=False)
"
```

### 4.2 导入到 Apifox

1. **创建项目**
   - 打开 Apifox
   - 点击 "新建项目"
   - 项目名称: `naicha-backend`
   - 选择 "导入数据" → "OpenAPI/Swagger"

2. **导入 OpenAPI 文档**
   - 选择 `openapi.json` 文件
   - 点击 "导入"
   - Apifox 会自动生成所有接口

3. **配置环境变量**
   
   在 Apifox 中创建 3 个环境：

   **本地环境 (Local)**
   ```
   base_url: http://localhost:8000
   admin_username: admin
   admin_password: admin123
   user_openid: mock-user-001
   ```

   **Staging 环境**
   ```
   base_url: https://staging-api.example.com
   admin_username: admin
   admin_password: <staging_password>
   user_openid: <real_wechat_openid>
   ```

   **生产环境 (Production)**
   ```
   base_url: https://api.example.com
   admin_username: <prod_admin>
   admin_password: <prod_password>
   ```

### 4.3 创建测试用例集

#### 测试集 1: 认证与授权

| 接口名称 | 测试场景 | 断言条件 |
|---------|---------|---------|
| 管理员登录 | 正常登录 | 返回 200 + JWT Token |
| 管理员登录 | 错误密码 | 返回 401 + 错误信息 |
| 用户登录 | 正常登录 | 返回 200 + JWT Token + 用户信息 |
| 获取用户资料 | 有效 Token | 返回 200 + 用户详情 |
| 获取用户资料 | 无 Token | 返回 401 |
| 获取用户资料 | 过期 Token | 返回 401 |

#### 测试集 2: 订单流程

| 接口名称 | 测试场景 | 断言条件 |
|---------|---------|---------|
| 创建订单 | 正常下单 | 返回 201 + 订单详情 |
| 创建订单 | 缺少 Idempotency-Key | 返回 400 |
| 创建订单 | 商品已下架 | 返回 400 + 错误提示 |
| 创建订单 | 库存不足 | 返回 409 |
| 创建订单 | 幂等键重复 | 返回相同订单 |
| 创建订单 | 并发请求 | 只创建 1 个订单 |
| 发起支付 | JSAPI 支付 | 返回 200 + prepay_id |
| 发起支付 | 订单不存在 | 返回 404 |
| 发起支付 | 订单已支付 | 返回 409 |
| 查询订单列表 | 分页查询 | 返回 200 + 订单数组 |

#### 测试集 3: 支付回调

| 接口名称 | 测试场景 | 断言条件 |
|---------|---------|---------|
| 微信支付回调 | 正常支付成功 | 返回 200 + SUCCESS |
| 微信支付回调 | 订单不存在 | 返回 404 |
| 微信支付回调 | 金额不匹配 | 返回 409 |
| 微信支付回调 | 重复通知 | 返回 200 (幂等) |
| 微信支付回调 | 签名错误 | 返回 401 |

#### 测试集 4: 管理后台

| 接口名称 | 测试场景 | 断言条件 |
|---------|---------|---------|
| POS 快速建单 | 现金支付 | 返回 200 + 已支付订单 |
| POS 快速建单 | 缺少 Idempotency-Key | 返回 400 |
| 静态码匹配 | 唯一匹配 | 返回 200 + 匹配结果 |
| 静态码匹配 | 多个候选 | 返回 409 + candidates |
| 静态码匹配 | 无候选 | 返回 404 |
| 更新库存状态 | 商品售罄 | 返回 200 + 审计日志 |
| 更新库存状态 | 非 admin 角色 | 返回 403 |
| 数据看板 | 查询今日数据 | 返回 200 + 统计数据 |
| 数据看板 | 对比昨日 | 返回 200 + compare_summary |

### 4.4 编写前置脚本

在 Apifox 中为需要认证的接口添加前置脚本：

```javascript
// 前置脚本: 自动登录获取 Token
pm.sendRequest({
    url: pm.environment.get('base_url') + '/api/v1/admin/login',
    method: 'POST',
    header: {
        'Content-Type': 'application/json',
    },
    body: {
        mode: 'raw',
        raw: JSON.stringify({
            username: pm.environment.get('admin_username'),
            password: pm.environment.get('admin_password')
        })
    }
}, function (err, res) {
    if (!err && res.code === 200) {
        const token = res.json().access_token;
        pm.environment.set('admin_token', token);
        console.log('✅ 自动登录成功');
    } else {
        console.log('❌ 登录失败:', err || res.body);
    }
});
```

为订单创建接口添加幂等键生成：

```javascript
// 前置脚本: 生成 Idempotency-Key
const idempotencyKey = 'test-' + Date.now() + '-' + Math.random().toString(36).substring(7);
pm.request.headers.add({
    key: 'X-Idempotency-Key',
    value: idempotencyKey
});
pm.environment.set('last_idempotency_key', idempotencyKey);
console.log('生成幂等键:', idempotencyKey);
```

### 4.5 编写后置断言

```javascript
// 后置脚本: 验证响应结构
pm.test("状态码为 200", function () {
    pm.response.to.have.status(200);
});

pm.test("响应时间 < 500ms", function () {
    pm.expect(pm.response.responseTime).to.be.below(500);
});

pm.test("返回 JSON 格式", function () {
    pm.response.to.be.json;
});

// 订单创建接口专用断言
pm.test("订单创建成功", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('order_id');
    pm.expect(jsonData).to.have.property('order_number');
    pm.expect(jsonData.status).to.eql('pending_payment');
    
    // 保存订单 ID 供后续接口使用
    pm.environment.set('last_order_id', jsonData.order_id);
});
```

### 4.6 执行测试集

1. **手动执行**
   - 选择测试集
   - 点击 "运行"
   - 查看测试报告

2. **自动化执行 (CI/CD 集成)**

   ```bash
   # 导出 Apifox 测试集为 JSON
   # 在 Apifox 中: 测试集 → 导出 → JSON 格式
   
   # 使用 Newman (Postman CLI) 执行
   npm install -g newman
   newman run apifox-collection.json \
     -e apifox-env-staging.json \
     --reporters cli,json \
     --reporter-json-export results.json
   ```

✅ **验收标准**:
- [ ] 所有核心接口测试通过
- [ ] 边界条件测试通过
- [ ] 并发测试通过 (使用 Apifox 批量运行)
- [ ] 性能断言达标 (P95 < 500ms)

---

## 阶段五：性能压测

### 5.1 准备压测环境

```bash
# 安装 Locust
pip install locust

# 确认压测脚本
ls -la infra/perf/
# 应包含: test_payment_only.py, run_150_concurrent_test.sh
```

### 5.2 基线压测 (50 并发)

```bash
cd infra/perf

# 运行 50 并发基线测试
locust -f test_payment_only.py \
  --headless \
  --host=https://staging-api.example.com \
  --users=50 \
  --spawn-rate=5 \
  --run-time=5m \
  --csv=../../perf_results/baseline_50u_$(date +%Y%m%d_%H%M%S) \
  --html=../../perf_results/baseline_50u_$(date +%Y%m%d_%H%M%S).html

# 预期结果:
# - RPS: ≥ 100 req/s
# - 平均响应时间: < 150ms
# - P95 响应时间: < 300ms
# - 错误率: 0%
```

### 5.3 压力测试 (100 并发)

```bash
locust -f test_payment_only.py \
  --headless \
  --host=https://staging-api.example.com \
  --users=100 \
  --spawn-rate=10 \
  --run-time=10m \
  --csv=../../perf_results/stress_100u_$(date +%Y%m%d_%H%M%S) \
  --html=../../perf_results/stress_100u_$(date +%Y%m%d_%H%M%S).html

# 预期结果:
# - RPS: ≥ 180 req/s
# - P95 响应时间: < 500ms
# - 错误率: < 0.1%
```

### 5.4 极限测试 (150 并发)

```bash
# 使用封装好的脚本
./run_150_concurrent_test.sh https://staging-api.example.com 10m

# 或手动执行
locust -f test_payment_only.py \
  --headless \
  --host=https://staging-api.example.com \
  --users=150 \
  --spawn-rate=10 \
  --run-time=10m \
  --csv=../../perf_results/limit_150u_$(date +%Y%m%d_%H%M%S) \
  --html=../../perf_results/limit_150u_$(date +%Y%m%d_%H%M%S).html

# 预期结果:
# - RPS: ≥ 250 req/s
# - P95 响应时间: < 800ms
# - P99 响应时间: < 1000ms
# - 错误率: < 0.5%
```

### 5.5 监控指标收集

在压测期间，同时监控以下指标：

```bash
# 终端 1: 实时日志
kubectl logs -n staging -l app=naicha-backend -f | grep -E "ERROR|WARNING"

# 终端 2: Prometheus 查询
# 访问: http://<prometheus_url>/graph

# 关键查询:
# 1. 错误率
rate(order_create_errors_total[1m]) / rate(order_create_total[1m])

# 2. P99 延迟
histogram_quantile(0.99, rate(order_create_latency_seconds_bucket[5m]))

# 3. DB 连接池使用率
db_pool_connections_used / (db_pool_size + db_pool_max_overflow)

# 4. 分布式锁失败率
rate(payment_match_attempt_total{result="lock_failed"}[1m])
```

### 5.6 性能基线记录

将测试结果记录到 `doc/perf-baseline.md`:

```markdown
## 压测结果 (2025-10-27 Staging 环境)

| 并发数 | RPS | 平均响应 | P95 | P99 | 错误率 |
|--------|-----|---------|-----|-----|--------|
| 50     | 120 | 85ms    | 180ms | 250ms | 0%     |
| 100    | 210 | 120ms   | 350ms | 480ms | 0.05%  |
| 150    | 280 | 180ms   | 680ms | 920ms | 0.3%   |

### 瓶颈分析
- 100 并发以下: CPU 使用率 < 60%, 无明显瓶颈
- 150 并发: DB 连接池使用率达 75%, 建议生产环境扩容
```

✅ **验收标准**:
- [ ] 50 并发零错误
- [ ] 100 并发错误率 < 0.1%
- [ ] 150 并发错误率 < 0.5%
- [ ] P99 延迟 < 1000ms
- [ ] 无 DB 连接池耗尽
- [ ] 无内存泄漏 (压测前后内存增长 < 20%)

---

## 阶段六：容灾演练

### 6.1 Redis 故障演练

```bash
cd infra/perf

# 1. 检查 Redis 初始状态
./redis_fault_drill.sh status
# 预期: ✅ Redis 172.21.48.1:6379 可达

# 2. 启动后台负载 (另一个终端)
locust -f test_payment_only.py \
  --headless -u 50 -r 5 -t 10m \
  --host=https://staging-api.example.com

# 3. 阻断 Redis (2 分钟后)
./redis_fault_drill.sh block

# 4. 观察降级行为 (持续 3 分钟)
kubectl logs -n staging -l app=naicha-backend -f | grep -E "redis|lock|cache"

# 预期日志:
# distributed_lock.client_unavailable: Redis client not available
# menu.cache.version_read_failed: Failed to read cache version from Redis
# Static QR match returned 409: Concurrent match request detected

# 5. 恢复 Redis
./redis_fault_drill.sh unblock

# 6. 验证系统恢复
./redis_fault_drill.sh status
# 预期: ✅ Redis 172.21.48.1:6379 可达

# 7. 检查 Locust 错误率
# 预期: 故障期间静态码匹配 409, 菜单读取仍正常
```

### 6.2 数据库连接池耗尽模拟

```bash
# 方法 1: 设置较小的连接池 (需重启服务)
kubectl set env deployment/naicha-backend \
  DATABASE_POOL_SIZE=5 \
  DATABASE_MAX_OVERFLOW=2 \
  -n staging

kubectl rollout status deployment/naicha-backend -n staging

# 方法 2: 持续高并发直到连接池耗尽
locust -f test_payment_only.py \
  --headless -u 200 -r 20 -t 5m \
  --host=https://staging-api.example.com

# 观察错误日志
kubectl logs -n staging -l app=naicha-backend -f | grep "pool.*timeout"

# 恢复连接池配置
kubectl set env deployment/naicha-backend \
  DATABASE_POOL_SIZE=20 \
  DATABASE_MAX_OVERFLOW=30 \
  -n staging
```

### 6.3 依赖服务降级验证

**场景 1: 打印服务不可用**

```bash
# 模拟打印服务返回 500
# (需临时修改 PRINTER_WEBHOOK_URL 或让打印服务返回错误)

# 创建 POS 订单观察行为
curl -X POST https://staging-api.example.com/api/v1/admin/orders \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Idempotency-Key: test-print-fail-$(date +%s)" \
  -d '{
    "items": [{"product_id": 1, "quantity": 1}],
    "payment_channel": "cash",
    "print_job": true
  }'

# 预期行为:
# - 订单创建成功
# - 打印任务入队，标记为 failed
# - 日志记录错误但不阻塞订单流程
# - Celery 后续会重试打印
```

**场景 2: 微信支付服务超时**

```bash
# 在 Locust 中增加支付超时场景
# 编辑 infra/perf/test_payment_only.py，添加超时模拟

# 观察服务行为:
# - 支付发起接口应返回 503 或 504
# - 不应影响其他用户的订单创建
```

### 6.4 快速回滚演练

```bash
# 1. 模拟有问题的版本部署
kubectl set image deployment/naicha-backend \
  naicha-backend=<registry>/naicha-backend:bad-version \
  -n staging

# 2. 等待部署完成
kubectl rollout status deployment/naicha-backend -n staging

# 3. 发现问题，立即回滚
kubectl rollout undo deployment/naicha-backend -n staging

# 4. 验证回滚成功
kubectl rollout status deployment/naicha-backend -n staging

# 5. 检查服务恢复
curl https://staging-api.example.com/health

# 计时: 从发现问题到服务恢复应 < 2 分钟
```

✅ **验收标准**:
- [ ] Redis 故障期间菜单读取仍可用
- [ ] Redis 恢复后 1 分钟内服务完全正常
- [ ] 连接池耗尽时有明确错误提示
- [ ] 打印服务故障不影响订单创建
- [ ] 回滚操作可在 2 分钟内完成

---

## 阶段七：生产配置审查

按照 `doc/production-readiness-checklist.md` 逐项检查。

### 7.1 环境变量检查脚本

```bash
#!/bin/bash
# 保存为 scripts/check_prod_env.sh

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 生产环境配置检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 在生产 Pod 中执行
POD_NAME=$(kubectl get pods -n production -l app=naicha-backend -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n production $POD_NAME -- bash -c '
echo "=== 限流配置 ==="
echo "RATE_LIMIT_DEFAULT_LIMITS: $RATE_LIMIT_DEFAULT_LIMITS"
echo "PERF_DISABLE_HTTP_OVERHEADS: ${PERF_DISABLE_HTTP_OVERHEADS:-未设置(正确)}"

echo ""
echo "=== JWT 配置 ==="
echo "JWT_EXPIRE_MINUTES: $JWT_EXPIRE_MINUTES"

echo ""
echo "=== 数据库配置 ==="
echo "DATABASE_POOL_SIZE: $DATABASE_POOL_SIZE"
echo "DATABASE_MAX_OVERFLOW: $DATABASE_MAX_OVERFLOW"

echo ""
echo "=== Redis 配置 ==="
echo "CELERY_BROKER_URL: ${CELERY_BROKER_URL%%@*}@***"  # 隐藏密码
'

echo ""
echo "=== Redis 连通性 ==="
redis-cli -h 172.21.48.1 PING && echo "✅ Redis 可达" || echo "❌ Redis 不可达"

echo ""
echo "=== 数据库迁移状态 ==="
kubectl exec -n production $POD_NAME -- alembic current

echo ""
echo "=== Prometheus 指标 ==="
METRICS_URL="http://$(kubectl get svc -n production naicha-backend -o jsonpath='{.status.loadBalancer.ingress[0].ip}'):8000/metrics"
curl -s $METRICS_URL | grep -c "order_create_total" && echo "✅ 指标已暴露" || echo "❌ 指标未暴露"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

### 7.2 安全配置审查

```bash
# 1. 检查敏感信息是否暴露
kubectl get configmap -n production -o yaml | grep -E "password|secret|key"
# 预期: 无明文密码

# 2. 检查 Secret 配置
kubectl get secret naicha-api-secrets -n production -o jsonpath='{.data}' | jq 'keys'
# 预期包含: DATABASE_URL, JWT_SECRET_KEY, WECHAT_PAY_API_V3_KEY

# 3. 检查 RBAC 权限
kubectl auth can-i --list --as=system:serviceaccount:production:naicha-backend -n production
# 预期: 仅有必要的权限

# 4. 检查网络策略
kubectl get networkpolicies -n production
# 预期: 限制 Pod 间通信
```

### 7.3 监控告警配置

```bash
# 1. 验证 Prometheus 规则已加载
curl http://<prometheus_url>/api/v1/rules | \
  jq '.data.groups[] | select(.name=="naicha_backend_alerts")'

# 2. 测试告警触发 (在 Staging 环境)
# 人为制造高错误率，观察告警是否在 5 分钟内触发

# 3. 验证告警通知渠道
# 确认钉钉/Slack/邮件已配置并测试发送
```

✅ **验收标准**:
- [ ] 所有环境变量符合生产要求
- [ ] 无敏感信息泄露
- [ ] 数据库迁移状态正确
- [ ] Prometheus 指标可访问
- [ ] 告警规则已加载
- [ ] 告警通知渠道可用

---

## 阶段八：灰度上线

### 8.1 灰度上线计划

```
Day 1: 10% 流量灰度
├─ 08:00  部署新版本到生产环境 (金丝雀 Pod)
├─ 09:00  配置 Ingress 灰度 10% 流量
├─ 10:00  开始监控
├─ 12:00  中期检查 (错误率、延迟、用户反馈)
├─ 15:00  下午检查
└─ 18:00  日终评审 (决定是否继续或回滚)

Day 2: 50% 流量扩大
├─ 10:00  扩大至 50% 流量
├─ 全天   密切监控
└─ 18:00  评审

Day 3-5: 100% 全量
├─ 10:00  全量上线
├─ 持续   72 小时密切监控
└─ Day 5  收尾评审与复盘
```

### 8.2 配置 Ingress 灰度

```yaml
# 保存为 canary-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: naicha-backend-canary
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"  # 10% 流量
spec:
  ingressClassName: nginx
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: naicha-backend-v3
            port:
              number: 8000
```

```bash
# 应用灰度配置
kubectl apply -f canary-ingress.yaml

# 验证流量分配
kubectl get ingress -n production
kubectl describe ingress naicha-backend-canary -n production

# 调整灰度比例 (50%)
kubectl patch ingress naicha-backend-canary -n production \
  -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/canary-weight":"50"}}}'

# 全量上线 (删除金丝雀 Ingress)
kubectl delete ingress naicha-backend-canary -n production
```

### 8.3 监控清单

在灰度期间，每 2 小时检查一次：

**Grafana Dashboard** (http://<grafana_url>/d/naicha-backend-p0)
- [ ] 请求吞吐量 (QPS) 是否正常
- [ ] 错误率是否 < 0.5%
- [ ] P95/P99 延迟是否符合 SLO
- [ ] DB 连接池使用率是否 < 85%
- [ ] Redis 命令延迟是否 < 10ms

**Prometheus 告警** (http://<prometheus_url>/alerts)
- [ ] 是否有 Firing 状态的告警
- [ ] 告警是否及时通知到值班人员

**业务日志**
```bash
# 实时查看错误日志
kubectl logs -n production -l app=naicha-backend,version=v3 -f | grep ERROR

# 统计每分钟错误数
kubectl logs -n production -l app=naicha-backend,version=v3 --since=1m | grep ERROR | wc -l
```

**用户反馈**
- [ ] 客服是否收到异常反馈
- [ ] 订单创建成功率是否正常
- [ ] 支付成功率是否正常

### 8.4 回滚决策矩阵

| 场景 | 阈值 | 决策 |
|------|------|------|
| 错误率 | > 1% 持续 5 分钟 | 立即回滚 |
| P99 延迟 | > 2000ms 持续 5 分钟 | 立即回滚 |
| DB 连接池 | 使用率 > 95% | 立即回滚 |
| 订单丢失 | 任意 1 单 | 立即回滚 |
| 重复扣款 | 任意 1 单 | 立即回滚 |
| Redis 故障 | 持续 > 10 分钟 | 评估后决定 |
| 用户投诉 | > 5 个/小时 | 评估后决定 |

### 8.5 回滚操作

```bash
# 方法 1: Kubernetes 原生回滚
kubectl rollout undo deployment/naicha-backend -n production
kubectl rollout status deployment/naicha-backend -n production

# 方法 2: 调整灰度比例为 0
kubectl patch ingress naicha-backend-canary -n production \
  -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/canary-weight":"0"}}}'

# 方法 3: 完全删除金丝雀
kubectl delete ingress naicha-backend-canary -n production
kubectl delete deployment naicha-backend-v3 -n production

# 验证回滚后服务正常
curl https://api.example.com/health
curl https://api.example.com/api/v1/menu
```

✅ **验收标准**:
- [ ] 10% 灰度阶段零严重事故
- [ ] 50% 灰度阶段业务指标正常
- [ ] 100% 全量后 72 小时稳定运行
- [ ] 回滚演练可在 2 分钟内完成

---

## 常见问题排查

### Q1: 本地测试通过，Staging 环境失败

**排查步骤**:
1. 检查环境变量差异: `env | grep -E "DATABASE|REDIS|JWT"`
2. 检查数据库迁移状态: `alembic current`
3. 检查网络连通性: `ping <db_host>`, `redis-cli -h <redis_host> PING`
4. 查看日志: `kubectl logs -n staging -l app=naicha-backend --tail=100`

### Q2: 压测时错误率突然飙升

**排查步骤**:
1. 检查 DB 连接池: `curl http://<url>/metrics | grep db_pool_connections_used`
2. 检查 Redis 连接: `redis-cli -h <host> INFO clients`
3. 检查 CPU/内存: `kubectl top pods -n staging`
4. 降低并发数重新测试

### Q3: Apifox 测试 Token 过期

**解决方案**:
1. 在集合设置中启用 "自动刷新 Token"
2. 或在每个请求前置脚本中重新登录获取 Token (见 4.4 节)

### Q4: 灰度期间如何查看新旧版本分别的指标

**解决方案**:
在 Prometheus 查询中使用 `version` 标签：

```promql
# 新版本错误率
rate(order_create_errors_total{version="v3"}[5m]) / 
rate(order_create_total{version="v3"}[5m])

# 旧版本错误率
rate(order_create_errors_total{version="v2"}[5m]) / 
rate(order_create_total{version="v2"}[5m])
```

### Q5: 数据库迁移在生产环境失败

**应急方案**:
1. 立即停止部署: `kubectl rollout pause deployment/naicha-backend -n production`
2. 检查迁移日志: `kubectl logs -n production <pod> | grep alembic`
3. 如果是数据问题，手动修复数据后重试
4. 如果是结构问题，回滚迁移: `alembic downgrade -1`
5. 修复迁移脚本后重新部署

---

## 附录：完整检查清单

### 上线前总检查清单

**代码质量**
- [ ] `make lint` 通过
- [ ] `make test` 通过 (128+ 测试用例)
- [ ] 代码覆盖率 ≥ 70%

**功能验证**
- [ ] 本地环境冒烟测试通过
- [ ] Staging 环境部署成功
- [ ] Apifox 全量测试通过 (100+ 用例)
- [ ] 关键路径手动验证通过

**性能验证**
- [ ] 50 并发零错误
- [ ] 100 并发错误率 < 0.1%
- [ ] 150 并发错误率 < 0.5%
- [ ] P99 延迟 < 1000ms

**容灾验证**
- [ ] Redis 故障演练通过
- [ ] 数据库连接池压力测试通过
- [ ] 依赖服务降级验证通过
- [ ] 快速回滚演练通过

**配置审查**
- [ ] 环境变量符合生产要求
- [ ] 数据库迁移状态正确
- [ ] 安全配置通过审核
- [ ] 监控告警规则已部署

**文档准备**
- [ ] API 文档已更新 (doc/api.md)
- [ ] 变更日志已编写 (CHANGELOG.md)
- [ ] 回滚 Runbook 已准备
- [ ] On-call 轮值表已更新

**团队准备**
- [ ] 技术团队已培训
- [ ] 客服团队已告知
- [ ] 应急联系方式已确认
- [ ] 灰度上线计划已评审

---

## 附录：工具与资源

### 推荐工具

| 工具 | 用途 | 下载地址 |
|------|------|---------|
| Apifox | API 测试 | https://apifox.com |
| Postman | API 测试 | https://postman.com |
| Locust | 性能压测 | https://locust.io |
| K6 | 性能压测 | https://k6.io |
| Newman | CLI API 测试 | npm install -g newman |
| Grafana | 监控看板 | https://grafana.com |
| Prometheus | 指标采集 | https://prometheus.io |

### 参考文档

- OpenAPI 规范: https://swagger.io/specification/
- Locust 压测最佳实践: https://docs.locust.io/en/stable/writing-a-locustfile.html
- Kubernetes 灰度发布: https://kubernetes.io/docs/concepts/cluster-administration/manage-deployment/#canary-deployments
- Site Reliability Engineering (SRE): https://sre.google/

---

**文档维护**: 请在每次上线后更新本文档，记录实际遇到的问题和解决方案。

**版本历史**:
- V1.0 (2025-10-27): 初版发布
