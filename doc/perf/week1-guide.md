# Week1 压测基线填写指南

> **目标**：完成 `doc/perf-baseline.md` 的 Locust/wrk/WebSocket 实测数据填写，并确保新指标落到 Prometheus。

---

## 📋 概述

本指南帮助你在 Week1 完成以下任务：

1. ✅ **执行完整压测**：运行 Locust、wrk、WebSocket 测试
2. ✅ **自动解析结果**：使用脚本自动填充 `perf-baseline.md`
3. ✅ **验证 Prometheus 指标**：确认新指标已正确暴露
4. ✅ **保存归档**：妥善保存 HTML 报告和日志

---

## 🚀 快速开始（推荐）

### 方式一：一键执行（最简单）

```bash
# 1. 设置环境变量
export PERF_BASE_URL="http://127.0.0.1:8000"           # 或 staging 地址
export PERF_USER_TOKEN="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwic2NvcGUiOiJ1c2VyIiwiZXhwIjoxNzYzNzA2OTkwfQ.DHLZwtGCYeQ905YFLqnFPkrO__JQsS5E1pEodpTI4Qo"            # 用户 Token
export PERF_ADMIN_TOKEN="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwic2NvcGUiOiJhZG1pbiIsImV4cCI6MTc2MzcwNjk5MH0.VdB2nozD-M8EIW88tIZiReAteL-cqA5QcVius0ZQ2Wo"         # 管理员 Token  
export PERF_SECRET_KEY="change_me"               # HMAC 密钥

# 2. 执行完整压测（约 5-10 分钟）
bash infra/perf/run_baseline.sh

# 3. 解析结果并更新文档
python infra/perf/parse_results.py --input ./perf_results

# 4. 查看生成的报告
open perf_results/locust_100u_*.html
```

### 方式二：使用 Makefile

```bash
# 添加到 Makefile 后执行
make perf-baseline
```

---

## 📝 详细步骤

### 步骤 1：环境准备

#### 1.1 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements-dev.txt

# 或仅安装压测工具
pip install locust websockets

# 如需 wrk（可选）
# macOS: brew install wrk
# Ubuntu: apt-get install wrk
```

#### 1.2 配置环境变量

创建 `.env.perf` 文件或直接 export：

```bash
# 必填项
export PERF_BASE_URL="http://127.0.0.1:8000"
export PERF_USER_TOKEN="Bearer <your-user-token>"
export PERF_SECRET_KEY="<your-hmac-secret>"

# 可选项
export PERF_ADMIN_TOKEN="Bearer <admin-token>"  # WebSocket 测试需要
export OUTPUT_DIR="./perf_results"              # 结果保存目录
```

**获取 Token 方法**：

```bash
# 本地开发环境
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
```

#### 1.3 验证服务可用性

```bash
# 检查健康端点
curl http://127.0.0.1:8000/healthz

# 检查 Prometheus 指标端点
curl http://127.0.0.1:8000/metrics | grep -E "order_create_total|payment_callback"
```

---

### 步骤 2：执行压测

#### 2.1 运行自动化脚本

```bash
# 赋予执行权限
chmod +x infra/perf/run_baseline.sh

# 执行完整压测
bash infra/perf/run_baseline.sh
```

**脚本会依次执行**：
- ✅ Locust 压测（100/200/500 并发，各 30 秒）
- ✅ wrk 基线测试（菜单 + 下单接口）
- ✅ WebSocket 连接测试（200 连接 × 120 秒）
- ✅ 收集 Prometheus 指标快照

**预计耗时**：5-10 分钟

#### 2.2 手动执行（可选）

如果需要单独测试某个模块：

```bash
# 仅 Locust（100 并发）
locust -f infra/perf/locustfile.py \
  --headless --users 100 --spawn-rate 20 --run-time 30s \
  --html locust_report.html

# 仅 WebSocket
python infra/perf/ws_runner.py \
  --connections 200 --duration 120 \
  --base-url "ws://127.0.0.1:8000/ws/merchant" \
  --token "$PERF_ADMIN_TOKEN"

# 仅 wrk（如果已安装）
wrk -t4 -c100 -d30s \
  -s infra/perf/scripts/menu.lua \
  "$PERF_BASE_URL"
```

---

### 步骤 3：解析结果并更新文档

#### 3.1 自动填充 perf-baseline.md

```bash
python infra/perf/parse_results.py \
  --input ./perf_results \
  --baseline ./doc/perf-baseline.md \
  --output-json ./perf_results/report.json
```

**脚本功能**：
- ✅ 解析 Locust CSV 统计文件（P50/P95/P99、QPS、错误率）
- ✅ 解析 wrk 输出（QPS、延迟）
- ✅ 解析 WebSocket 日志（心跳延迟、广播统计）
- ✅ 自动更新 `perf-baseline.md` 表格中的"待填"占位符
- ✅ 导出 JSON 格式报告（可选）

#### 3.2 手动验证填充结果

```bash
# 查看更新后的文档
cat doc/perf-baseline.md | grep -A 10 "Locust 压测指标"

# 验证是否还有未填项
grep "待填" doc/perf-baseline.md
```

---

### 步骤 4：验证 Prometheus 指标

#### 4.1 检查指标端点

```bash
# 访问 /metrics 端点
curl http://127.0.0.1:8000/metrics > metrics_snapshot.txt

# 检查关键业务指标
grep -E "order_create_total|payment_callback_latency|menu_cache" metrics_snapshot.txt
```

#### 4.2 必须存在的指标

根据 `prometheus-rules.yaml` 和代码中的定义，以下指标必须存在：

| 指标名称 | 类型 | 说明 | 来源文件 |
|---------|------|------|----------|
| `order_create_total{result="success\|error"}` | Counter | 订单创建计数 | `app/metrics/orders.py` |
| `payment_callback_total{result="..."}` | Counter | 支付回调计数 | `app/metrics/payments.py` |
| `payment_callback_latency_ms` | Histogram | 支付回调耗时 | `app/metrics/payments.py` |
| `payment_match_attempt_total{result="..."}` | Counter | 静态码匹配计数 | `app/metrics/payments.py` |
| `admin_order_created_total{result="..."}` | Counter | POS 建单计数 | `app/metrics/admin_orders.py` |
| `admin_order_create_latency_ms` | Histogram | POS 建单耗时 | `app/metrics/admin_orders.py` |
| `admin_dashboard_query_latency_ms` | Histogram | 看板查询耗时 | `app/metrics/dashboard.py` |
| `menu_cache_lookup_total{result="hit\|miss"}` | Counter | 菜单缓存命中率 | `app/metrics/menu.py` |

**验证命令**：

```bash
# 检查是否全部存在
for metric in order_create_total payment_callback_total payment_callback_latency_ms admin_order_create_latency_ms menu_cache_lookup_total; do
  echo -n "$metric: "
  grep -c "^${metric}" metrics_snapshot.txt
done
```

#### 4.3 补充缺失指标（如果需要）

如果某些指标不存在，请检查：

1. **服务代码中是否已调用指标**：

```python
# 示例：在 app/services/orders.py 中
from app.metrics.orders import ORDER_CREATE_TOTAL

async def create_order(...):
    try:
        # ... 业务逻辑
        ORDER_CREATE_TOTAL.labels(result="success").inc()
    except Exception:
        ORDER_CREATE_TOTAL.labels(result="error").inc()
        raise
```

2. **Prometheus 端点是否启用**：

```bash
# 检查环境变量
echo $PROMETHEUS_ENABLED  # 应为 true 或未设置（默认启用）

# 或查看 app/core/settings.py
grep prometheus_enabled app/core/settings.py
```

3. **指标是否在模块 `__init__.py` 中导出**：

```python
# app/metrics/__init__.py
from app.metrics.orders import *
from app.metrics.payments import *
from app.metrics.admin_orders import *
# ...
```

---

### 步骤 5：归档和提交

#### 5.1 保存压测报告

```bash
# 创建归档目录
mkdir -p doc/perf/reports/week1_$(date +%Y%m%d)

# 复制结果文件
cp -r perf_results/* doc/perf/reports/week1_$(date +%Y%m%d)/

# 记录 Git 提交号
git rev-parse HEAD > doc/perf/reports/week1_$(date +%Y%m%d)/git_commit.txt
```

#### 5.2 更新填写信息

在 `doc/perf-baseline.md` 顶部补充：

```markdown
> 填写人：你的名字  
> 上次更新：2025-10-21 14:30:00  
> 数据来源：`locust` HTML 报告、`ws_runner.py` 汇总
```

#### 5.3 提交到 Git

```bash
# 添加变更
git add doc/perf-baseline.md
git add infra/perf/run_baseline.sh
git add infra/perf/parse_results.py
git add doc/perf/week1-guide.md
git add doc/perf/reports/

# 提交
git commit -m "feat: 完成 Week1 压测基线数据填写

- 执行 Locust 100/200/500 并发压测
- 补充 wrk 基线和 WebSocket 测试
- 验证 Prometheus 指标暴露
- 归档 HTML 报告和 JSON 结果"
```

---

## 🔍 结果解读

### Locust 指标判断标准

根据 SLO 目标：

| 接口 | P95 阈值 | 错误率阈值 |
|------|----------|-----------|
| `GET /api/v1/menu` | ≤ 40ms | < 0.1% |
| `POST /api/v1/orders` | ≤ 200ms | < 0.5% |
| `POST /api/v1/payments/notify/wechat` | ≤ 120ms | < 0.1% |

**不达标处理**：
- P95 超标 → 查看 `doc/perf/pool-config-diff.md`，检查数据库连接池配置
- 错误率高 → 查看应用日志 `kubectl logs` 或本地 `uvicorn.log`
- QPS 低 → 检查 CPU/内存资源限制

### WebSocket 指标判断标准

| 指标 | 目标值 |
|------|--------|
| 连接成功率 | 100% (200/200) |
| 心跳 P95 | < 100ms |
| 心跳 P99 | < 200ms |
| 订单广播校验失败 | 0 |

**不达标处理**：
- 连接失败 → 检查 Token 有效性和 WebSocket 路由配置
- 心跳延迟高 → 检查网络 RTT 和服务负载
- 广播校验失败 → 查看 `ws_runner.py` 中的 `validate_order_broadcast` 逻辑

### Prometheus 指标健康检查

```bash
# 检查指标是否正常递增
curl http://127.0.0.1:8000/metrics | grep order_create_total

# 预期输出示例：
# order_create_total{result="success"} 1234.0
# order_create_total{result="error"} 5.0
```

**注意**：
- Counter 应只增不减
- Histogram 应有多个 bucket（`_bucket{le="..."}` 系列）
- 错误率 = `error / (success + error)` 应低于阈值

---

## ⚠️ 常见问题

### 1. Locust 报错：`No module named 'locust'`

```bash
pip install locust
```

### 2. wrk 命令找不到

wrk 是 C 编写的工具，需单独安装：

```bash
# macOS
brew install wrk

# Ubuntu/Debian
sudo apt-get install wrk

# 或跳过 wrk 测试（非必需）
```

### 3. WebSocket 连接失败

```bash
# 检查 Token 格式（需要 Bearer 前缀）
echo $PERF_ADMIN_TOKEN | grep -q "Bearer" || echo "缺少 Bearer 前缀"

# 检查 WebSocket 路由
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test" \
  "http://127.0.0.1:8000/ws/merchant?token=<token>"
```

### 4. /metrics 端点返回 403

检查 `settings.PROMETHEUS_ENABLED`：

```python
# app/core/settings.py
prometheus_enabled: bool = True
```

或通过环境变量：

```bash
export PROMETHEUS_ENABLED=true
```

### 5. 解析脚本找不到 CSV 文件

Locust 生成的文件名格式：
- `locust_100u_20250421_120000_stats.csv`
- `locust_100u_20250421_120000_stats_history.csv`
- `locust_100u_20250421_120000.html`

确认 `--csv` 参数正确：

```bash
locust ... --csv "perf_results/locust_100u_$(date +%Y%m%d_%H%M%S)"
```

---

## 📚 参考资料

- **压测工具文档**：
  - [Locust 官方文档](https://docs.locust.io/)
  - [wrk GitHub](https://github.com/wg/wrk)
  
- **项目相关文档**：
  - `infra/perf/README.md` - 压测准备与环境配置
  - `doc/perf/pool-config-diff.md` - 连接池调优指南
  - `doc/perf/staging-checklist.md` - 环境验收清单

- **Prometheus 指标**：
  - `infra/k8s/prometheus-rules.yaml` - 告警规则
  - `app/metrics/` - 业务指标定义

---

## ✅ 验收清单

完成以下所有项后，Week1 压测任务即可通过：

- [ ] `doc/perf-baseline.md` 中的 Locust 表格已填写（100/200/500 并发）
- [ ] 所有关键接口 P95 达标（菜单 ≤40ms，下单 ≤200ms，支付回调 ≤120ms）
- [ ] WebSocket 表格已填写（200 连接，心跳 P95/P99，广播统计）
- [ ] `/metrics` 端点返回所有必需指标（见上文表格）
- [ ] HTML 报告已归档到 `doc/perf/reports/week1_<日期>/`
- [ ] Git 提交包含完整的压测结果和更新的文档
- [ ] 填写人和更新时间已补充到 `perf-baseline.md` 顶部

---

**🎉 完成以上步骤后，你的 Week1 压测任务就圆满完成了！**
