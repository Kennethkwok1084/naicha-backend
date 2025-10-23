# 性能测试环境配置手册

> **用途**：快速复制此配置以复现 100 并发零错误压测环境  
> **更新时间**：2025-10-23  
> **测试目标**：支付回调专项压测（订单创建 + 支付回调）

---

## 📋 配置清单

### 1. 数据库连接池（✅ 保留用于生产）

**文件**: `app/db/session.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker

engine: AsyncEngine = create_async_engine(
    settings.database_runtime_url,
    pool_size=200,        # 基础连接池大小（从默认 50 扩容）
    max_overflow=250,     # 溢出连接数（从默认 30 扩容）
    pool_pre_ping=True,   # 连接前健康检查
    pool_recycle=3600,    # 1小时回收连接，防止长连接失效
)
# 总计 450 并发连接，支持约 100-150 并发用户
```

**说明**：
- 每个支付回调需要 4 次数据库操作（SELECT+INSERT+UPDATE+INSERT）
- 每个操作持有连接约 1.5ms，总计约 6ms/请求
- 100 并发用户 × 2 请求（订单+回调）= 需要约 200 个同时连接
- 450 连接池提供足够缓冲空间

---

### 2. 环境变量（⚠️ 仅性能测试）

**文件**: `.env`

```bash
# ===== 性能测试专用配置 =====
# ⚠️ 生产环境必须移除以下配置

# 禁用 HTTP 中间件（CORS、GZip、ProxyHeaders）
# 用途：消除中间件性能开销，获得准确的业务逻辑性能数据
PERF_DISABLE_HTTP_OVERHEADS=true

# 支付回调签名密钥（用于 HMAC-SHA256 验证）
# 用途：与 Locust 测试脚本保持一致
export PERF_SECRET_KEY='change_me'

# 可选：用户认证 token（如需测试需登录的接口）
PERF_USER_TOKEN=

# ===== 数据库配置 =====
DATABASE_URL=postgresql+asyncpg://kwok:Onjuju1084@172.21.48.1:5432/naicha
```

**生产环境清理**：
```bash
# 删除或注释掉这些行
# PERF_DISABLE_HTTP_OVERHEADS=true
# PERF_SECRET_KEY=change_me
```

---

### 3. 限流器禁用（⚠️ 仅性能测试）

#### 3.1 禁用限流器初始化

**文件**: `app/main.py`

```python
# 注释掉限流器初始化
# init_rate_limiter(app)  # 临时禁用限流以进行性能测试
```

**生产环境还原**：
```python
# 取消注释
init_rate_limiter(app)
```

---

#### 3.2 禁用路由装饰器 - 支付回调

**文件**: `app/api/routes/payments.py`

```python
@router.post(
    "/notify/wechat",
    response_model=PaymentNotifyResponseSchema,
    status_code=200,
    name="wechat_payment_callback",
)
# @limiter.limit("18000/minute;300/second")  # 临时禁用限流
async def wechat_payment_callback(
    payload: PaymentNotifyPayloadSchema = Body(...),
    signature: str = Header(..., alias="X-Signature"),
    payment_service: PaymentService = Depends(get_payment_service),
):
    ...
```

**生产环境还原**：
```python
@limiter.limit("18000/minute;300/second")
async def wechat_payment_callback(...):
```

---

#### 3.3 禁用路由装饰器 - 订单创建

**文件**: `app/api/routes/orders/__init__.py`

```python
@router.post(
    "",
    response_model=OrderResponseSchema,
    status_code=201,
    name="create_order",
)
# @limiter.limit("3000/minute")  # 临时禁用限流
async def create_order(
    payload: CreateOrderSchema,
    session: AsyncSession = Depends(get_db),
    current_identity: dict = Depends(require_auth(allow_guest=True)),
):
    ...
```

**生产环境还原**：
```python
@limiter.limit("3000/minute")
async def create_order(...):
```

---

### 4. Locust 测试脚本

**文件**: `infra/perf/test_payment_only.py`

```python
import os
import hmac
import hashlib
import json
from locust import HttpUser, task, between

class PaymentUser(HttpUser):
    wait_time = between(1.0, 2.0)  # 用户思考时间 1-2 秒
    host = "http://127.0.0.1:8000"
    
    def on_start(self):
        """初始化：获取签名密钥"""
        self.secret_key = os.getenv("PERF_SECRET_KEY", "change_me")
    
    @task
    def payment_flow(self):
        """完整支付流程：创建订单 → 支付回调"""
        
        # 1. 创建订单
        order_data = {
            "items": [{"product_id": 1, "quantity": 1, "customizations": []}],
            "guest_session_id": "guest-perf-001",  # ⚠️ 必需字段
            "delivery_method": "dine_in"
        }
        
        with self.client.post(
            "/api/v1/orders",
            json=order_data,
            catch_response=True,
            name="POST /api/v1/orders"
        ) as order_resp:
            if order_resp.status_code == 201:
                order_number = order_resp.json()["order_number"]
                order_resp.success()
                
                # 2. 生成支付回调签名
                payload_dict = {
                    "order_number": order_number,
                    "amount": 100,
                    "channel": "wechat",
                    "transaction_id": f"wx_{order_number}"
                }
                payload_str = json.dumps(payload_dict, separators=(',', ':'))
                signature = hmac.new(
                    self.secret_key.encode(),
                    payload_str.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                # 3. 发送支付回调
                with self.client.post(
                    "/api/v1/payments/notify/wechat",
                    json=payload_dict,
                    headers={"X-Signature": signature},
                    catch_response=True,
                    name="POST /api/v1/payments/notify/wechat"
                ) as payment_resp:
                    if payment_resp.status_code == 200:
                        payment_resp.success()
                    else:
                        payment_resp.failure(f"Payment callback failed: {payment_resp.status_code}")
            else:
                order_resp.failure(f"Order creation failed: {order_resp.status_code}")
```

---

## 🚀 执行步骤

### Step 1: 准备数据库

```bash
# 1. 重置 pg_stat_statements 统计（可选，用于性能分析）
PGPASSWORD=Onjuju1084 psql -h 172.21.48.1 -U kwok -d naicha -c \
  "SELECT public.pg_stat_statements_reset();"

# 2. 验证数据库连接
PGPASSWORD=Onjuju1084 psql -h 172.21.48.1 -U kwok -d naicha -c \
  "SELECT version();"
```

---

### Step 2: 启动应用

```bash
# 在项目根目录执行
cd /home/kwok/coder/naicha-backend

# 确保环境变量已配置
cat .env | grep PERF_

# 启动 Uvicorn（开发模式）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 或使用 Makefile（推荐）
make dev
```

**验证启动成功**：
```bash
curl http://127.0.0.1:8000/health
# 预期输出：{"status":"ok"}
```

---

### Step 3: 运行 100 并发压测

```bash
# 在另一个终端执行
cd /home/kwok/coder/naicha-backend

# 运行 Locust（100 并发，持续 60 秒）
locust -f infra/perf/test_payment_only.py \
  --headless \
  --users 100 \
  --spawn-rate 10 \
  --run-time 60s \
  --host http://127.0.0.1:8000 \
  --html perf_results/payment_100u_$(date +%Y%m%d_%H%M%S).html \
  --csv perf_results/payment_100u_$(date +%Y%m%d_%H%M%S)

# 参数说明：
# --users 100          : 100 个并发用户
# --spawn-rate 10      : 每秒启动 10 个用户（10 秒达到峰值）
# --run-time 60s       : 运行 60 秒
# --headless           : 无界面模式（命令行输出）
# --html               : 生成 HTML 报告
# --csv                : 生成 CSV 数据文件
```

**预期结果**：
```
Type     Name                                      # reqs      # fails  |     Avg     Min     Max  Median  |   req/s
--------|-----------------------------------------------|-------|-------------|-------|-------|-------|--------|--------
POST     /api/v1/orders                                2699         0  |      25      10     150      20  |   45.00
POST     /api/v1/payments/notify/wechat                2679         0  |      25      10     180      20  |   45.00
--------|-----------------------------------------------|-------|-------------|-------|-------|-------|--------|--------
         Aggregated                                    5378         0  |      25      10     180      20  |   90.15

Response time percentiles (approximated):
Type     Name                                                  50%    66%    75%    80%    90%    95%    98%    99%  99.9% 99.99%   100%
--------|-------------------------------------------------------|------|------|------|------|------|------|------|------|------|------|------|
POST     /api/v1/orders                                         25     30     40     50     70    100    150    200    270    300    350
POST     /api/v1/payments/notify/wechat                         25     30     40     50     70    100    150    200    270    300    350
--------|-------------------------------------------------------|------|------|------|------|------|------|------|------|------|------|------|
         Aggregated                                             25     30     40     50     70    100    150    200    270    300    350

# ✅ 0% 错误率
# ✅ P50 = 25ms
# ✅ P95 = 100ms
# ✅ P99 = 270ms
# ✅ QPS = 90.15 req/s
```

---

### Step 4: 分析数据库性能

```bash
# 查询 SQL 性能统计
PGPASSWORD=Onjuju1084 psql -h 172.21.48.1 -U kwok -d naicha -c "
SELECT 
  round(total_exec_time::numeric,2) total_ms,
  calls,
  round(mean_exec_time::numeric,2) mean_ms,
  round((total_exec_time/sum(total_exec_time) OVER ())*100, 2) pct,
  left(query,80) sample
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_statements%'
ORDER BY total_exec_time DESC
LIMIT 10;
"
```

**预期输出**（100 并发）：
```
 total_ms | calls | mean_ms |  pct  |                                     sample                                      
----------+-------+---------+-------+--------------------------------------------------------------------------------
  3000.00 |  2700 |    1.11 | 45.00 | SELECT orders.* FROM orders WHERE order_number = $1
   700.00 |  2700 |    0.26 | 10.50 | INSERT INTO payment_records (...) VALUES (...)
   600.00 |  2700 |    0.22 | 9.00  | INSERT INTO order_items (...) VALUES (...)
   500.00 |  2700 |    0.19 | 7.50  | INSERT INTO orders (...) VALUES (...)
   450.00 |  2700 |    0.17 | 6.75  | INSERT INTO print_jobs (...) VALUES (...)
   400.00 |  2700 |    0.15 | 6.00  | UPDATE orders SET status = $1, paid_at = $2 WHERE order_id = $3

# ✅ 所有查询 < 2ms
# ✅ SELECT 占比 45%（正常，业务逻辑需要）
# ✅ 无慢查询
```

---

### Step 5: 可选 - py-spy 性能分析

```bash
# 1. 获取 Uvicorn 进程 PID
ps aux | grep uvicorn
# 输出示例：kwok  66281  ... uvicorn app.main:app

# 2. 运行 py-spy（需要 sudo 权限）
sudo /home/kwok/coder/naicha-backend/.venv/bin/py-spy record \
  -o perf_results/pyspy_100u.svg \
  -d 90 \
  --pid 66281

# 3. 同时在另一个终端运行 Locust（参考 Step 3）

# 4. 完成后查看火焰图
xdg-open perf_results/pyspy_100u.svg
# 或在浏览器打开该文件
```

---

## 📊 性能基线

### ✅ 100 并发（推荐生产配置）

| 指标 | 数值 | SLO 目标 | 状态 |
|------|------|----------|------|
| 错误率 | **0%** | < 0.5% | ✅ 达标 |
| 吞吐量 | **90 req/s** | - | ✅ 优秀 |
| P50 延迟 | **25ms** | - | ✅ 优秀 |
| P95 延迟 | **100ms** | ≤ 120ms | ✅ 达标 |
| P99 延迟 | **270ms** | - | ✅ 良好 |
| 最慢 SQL | **1.54ms** | < 10ms | ✅ 优秀 |
| 连接池使用 | **200/450** | < 80% | ✅ 健康 |

**结论**：100 并发是当前架构的**安全运营线**。

---

### ❌ 200 并发（架构瓶颈）

| 指标 | 数值 | SLO 目标 | 状态 |
|------|------|----------|------|
| 错误率 | **21.24%** | < 0.5% | ❌ 超标 42 倍 |
| 吞吐量 | **114 req/s** | - | ⚠️ 受错误影响 |
| P50 延迟 | **440ms** | - | ⚠️ 退化 17 倍 |
| P95 延迟 | **1000ms** | ≤ 120ms | ❌ 超标 8.3 倍 |
| P99 延迟 | **1400ms** | - | ❌ 超标 11.7 倍 |
| 最慢 SQL | **1.54ms** | < 10ms | ✅ SQL 层正常 |
| 连接池使用 | **450/450** | < 80% | ❌ 耗尽 |
| 事务回滚率 | **49.8%** | < 1% | ❌ 连接不足 |

**结论**：200 并发超出架构承载能力，需要以下升级：
- 消息队列（Celery + RabbitMQ）异步化支付回调
- 读写分离（PostgreSQL 主从复制）
- PgBouncer 事务模式连接池

---

## ⚠️ 生产环境清理检查表

在部署到生产环境前，务必完成以下还原：

- [ ] **还原限流器**：取消注释 `app/main.py` 中的 `init_rate_limiter(app)`
- [ ] **还原路由装饰器**：取消注释所有 `@limiter.limit()` 装饰器
- [ ] **移除测试环境变量**：删除 `.env` 中的 `PERF_DISABLE_HTTP_OVERHEADS=true`
- [ ] **保留连接池配置**：`pool_size=200, max_overflow=250` 可保留
- [ ] **调整限流阈值**：根据实际流量调整（建议 `1000/minute` 防止攻击）
- [ ] **启用监控**：确保 Prometheus + Grafana 正常采集指标
- [ ] **配置告警**：数据库连接池使用率 > 70% 时触发告警

---

## 📚 相关文档

- [压测基线记录](./perf-baseline.md) - 历史压测结果和优化记录
- [开发环境搭建](./develop.md) - 本地开发环境配置
- [API 文档](./api.md) - 接口规范和示例
- [运维手册](./runbook.md) - 生产环境部署和故障排查

---

## 🔧 故障排查

### 问题 1：Locust 报错 400 Bad Request

**症状**：
```
POST /api/v1/orders: 400 Bad Request
{"detail":"Guest session required"}
```

**解决方案**：
确保 `order_data` 包含 `guest_session_id` 字段：
```python
order_data = {
    "items": [...],
    "guest_session_id": "guest-perf-001"  # 必需
}
```

---

### 问题 2：支付回调返回 403 Forbidden

**症状**：
```
POST /api/v1/payments/notify/wechat: 403 Forbidden
{"detail":"Invalid signature"}
```

**解决方案**：
检查 `.env` 中的 `PERF_SECRET_KEY` 与测试脚本一致：
```bash
# .env
export PERF_SECRET_KEY='change_me'

# 测试脚本
self.secret_key = os.getenv("PERF_SECRET_KEY", "change_me")
```

---

### 问题 3：429 Too Many Requests

**症状**：
```
POST /api/v1/payments/notify/wechat: 429 Too Many Requests
{"detail":"Rate limit exceeded"}
```

**解决方案**：
确保已注释掉所有 `@limiter.limit()` 装饰器和 `init_rate_limiter(app)`。

---

### 问题 4：数据库连接超时

**症状**：
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 200 overflow 250 reached
```

**解决方案**：
1. 检查并发数是否超过 150（当前架构上限）
2. 检查数据库是否有慢查询：
   ```bash
   PGPASSWORD=Onjuju1084 psql -h 172.21.48.1 -U kwok -d naicha -c \
     "SELECT * FROM pg_stat_statements WHERE mean_exec_time > 10 ORDER BY mean_exec_time DESC;"
   ```
3. 考虑引入 PgBouncer 或消息队列

---

## 📞 联系支持

遇到问题？联系团队：
- 技术负责人：@Copilot
- 文档维护：见 Git blame
- 紧急故障：查看 [runbook.md](./runbook.md)
