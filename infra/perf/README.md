# 压测准备（Week 0.5）

> 目标：在正式压测前 2-3 天完成环境、脚本与校验，保障 Week1 可以直接进入性能验证。

- **基础配置**
- **脚本说明**
- **执行指令**
- **验收目标**

---

## 基础配置
- `kubectl get pods -n staging` 应全部为 `Running`，并包含 `naicha-api`、`naicha-worker`、`postgres`、`redis`、`celery-beat`。
- `kubectl port-forward svc/naicha-api 8000:80 -n staging` 后执行 `curl http://127.0.0.1:8000/healthz` 返回 200。
- 导入脱敏快照后，通过 `psql` 确认 `orders`、`payments`、`users` 表行数与快照记录一致。
- `redis-cli -h <redis-host>` 执行 `PING` 返回 `PONG`；`info memory` 显示 `used_memory_human < 256MB`。
- Celery 任务检查：`kubectl logs deployment/naicha-worker -n staging | tail` 出现 `beat.sync` / `task.received` 日志。

---

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `PERF_BASE_URL` | 压测目标地址（含协议） | `https://staging.api.example.com` |
| `PERF_USER_TOKEN` | 用户 Bearer Token（下单鉴权） | `eyJhb...` |
| `PERF_ADMIN_TOKEN` | 管理员 Token（WS 鉴权） | `eyJh...` |
| `PERF_SECRET_KEY` | HMAC 密钥（支付回调签名） | `super-secret-key` |
| `PERF_ORDER_TEMPLATE` | 订单模板路径（可覆盖默认） | `infra/perf/payloads/order_template.json` |
| `PERF_PAYMENT_RATIO` | 支付回调任务触发概率（0-1） | `0.3` |
| `WRK_BEARER_TOKEN` | `wrk` 下单脚本鉴权 | 同 `PERF_USER_TOKEN` |
| `WRK_IDEMPOTENCY_PREFIX` | `wrk` 幂等键前缀 | `wrk-perf` |

---

## 脚本概览

| 文件 | 作用 |
|------|------|
| `locustfile.py` | 主体压测（菜单、下单、支付回调链路），支持签名与参数化。 |
| `payloads/order_template.json` | 脱敏数据模板，包含可用 `product_id` / 规格组合。 |
| `scripts/menu.lua` | `wrk` 压菜单接口基线性能。 |
| `scripts/order_create.lua` | `wrk` 下单并生成动态幂等键。 |
| `ws_runner.py` | WebSocket 并发连接与心跳校验。 |

---

## Locust 执行

### 方式 1：使用 Makefile（推荐）

```bash
# 安装依赖（首次运行）
make install-dev

# 快速压测（100 并发 × 30 秒）
export PERF_BASE_URL="https://staging.api.example.com"
export PERF_USER_TOKEN="BearerTokenHere"
export PERF_ADMIN_TOKEN="AdminTokenHere"
export PERF_SECRET_KEY="super-secret"
make perf-locust
```

### 方式 2：直接使用 Locust

```bash
pip install -U locust websockets
export PERF_BASE_URL="https://staging.api.example.com"
export PERF_USER_TOKEN="BearerTokenHere"
export PERF_ADMIN_TOKEN="AdminTokenHere"
export PERF_SECRET_KEY="super-secret"

locust -f infra/perf/locustfile.py --users 100 --spawn-rate 20
```

### 任务权重
- GET `/api/v1/menu`：权重 5（浏览量最高的核心接口）
- POST `/api/v1/orders`：权重 3（自动附带幂等键与鉴权）
- POST `/api/v1/payments/notify/wechat`：权重 1（默认以 `PERF_PAYMENT_RATIO=0.3` 概率触发，模拟外部回调）
- WebSocket 心跳：场景任务（可选），默认每 30 秒自检

---

## wrk 脚本

菜单接口基线：
```bash
export PERF_BASE_URL="https://staging.api.example.com"
wrk -t4 -c100 -d30s -H "Host: api.example.com" -s infra/perf/scripts/menu.lua "$PERF_BASE_URL"
```

下单链路（需先更新 `ORDER_BODY` 内的产品与规格 ID）：
```bash
export WRK_BEARER_TOKEN="$PERF_USER_TOKEN"
wrk -t2 -c30 -d60s -s infra/perf/scripts/order_create.lua "$PERF_BASE_URL"
```

---

## WebSocket 校验

### 方式 1：使用 Makefile（推荐）

```bash
export PERF_ADMIN_TOKEN="AdminTokenHere"
export PERF_WS_URL="wss://staging.api.example.com/ws/merchant"
make perf-ws
```

### 方式 2：直接运行脚本

```bash
python infra/perf/ws_runner.py --connections 200 --duration 120 \
  --base-url "wss://staging.api.example.com/ws/merchant" \
  --token "$PERF_ADMIN_TOKEN"
```

输出应包含：
- `connected=200` 且无持续错误
- 心跳延迟 `< 2s`
- 返回的 `order.paid` 广播 payload 字段齐全（`order_id/order_number/status/total_price/paid_at`）

---

## 异常排查
- **连接失败**：检查 `PERF_BASE_URL`/`PERF_WS_URL` 与 TLS 证书；使用 `curl -kv` 验证。
- **签名错误**：确认 `PERF_SECRET_KEY` 与服务端配置一致，可抓包对比 `X-Wechat-Signature`。
- **429 或限流**：调低 `--spawn-rate` 或调整 `nginx.ingress.kubernetes.io/limit-rps`。
- **超时/502**：查看 `kubectl logs deployment/naicha-api -n staging`，关注数据库耗时与 Redis 连接数。
- **WebSocket 校验失败**：`ws_runner.py` 报告 `订单广播校验失败` 时，检查服务端广播 JSON 结构。

---

## 结果解读
- Locust 终端输出关注 `Median (ms)`、`95%`、`Failures`，并将指标记录到 `doc/perf-baseline.md`。
- `locust --html report.html` 生成的报告重点查看 **Request Statistics** 与 **Response Time Distribution**。
- 若 `POST /orders` `95%` > 200ms 或错误率 > 0.5%，需要进入瓶颈分析流程（见 `doc/perf/pool-config-diff.md`）。
- WebSocket 汇总应显示 `订单广播` 数量与 `订单广播校验失败=0`；如超出，回放 `merchant_notifier` 日志。
- Prometheus 重点观察：`order_create_total{result="success"}`、`payment_callback_latency_ms`、`menu_cache_hit_rate`；若发现 `service_error`/`unexpected_error` 标签增长需立即排查日志。

---

## Week 0.5 验收
- ✅ 脱敏数据与服务运行检查记录于 `doc/perf/staging-checklist.md`
- ✅ 压测脚本提交并自测通过（本地最小运行：`make perf-locust` 或 `locust --headless -u1 -r1 -t10s`）
- ✅ wrk/WS 辅助脚本能单机运行且提供可复制命令
- ✅ README 内运行步骤与指标说明完整
- ✅ Python 依赖已补充到 `requirements-dev.txt`
