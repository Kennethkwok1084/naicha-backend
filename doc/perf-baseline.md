# 压测基线记录（Week 0.5 模板）

> 填写人：待补充  
> 上次更新：待补充  
> 数据来源：`locust` 终端输出 / HTML 报告、`wrk` 结果、`ws_runner.py` 汇总

---

## 1. Locust 压测指标

| 并发 | 接口 | P50(ms) | P95(ms) | P99(ms) | 错误率 | QPS | 备注 |
|------|------|---------|---------|---------|--------|-----|------|
| 100 | GET /api/v1/menu | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 100 | POST /api/v1/orders | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 100 | POST /api/v1/payments/notify/wechat | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 200 | GET /api/v1/menu | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 200 | POST /api/v1/orders | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 200 | POST /api/v1/payments/notify/wechat | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 500 | GET /api/v1/menu | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 500 | POST /api/v1/orders | 待填 | 待填 | 待填 | 待填 | 待填 |  |
| 500 | POST /api/v1/payments/notify/wechat | 待填 | 待填 | 待填 | 待填 | 待填 |  |

> SLO 目标：`/menu P95 ≤ 40ms`、`/orders P95 ≤ 200ms`、`/payments/notify P95 ≤ 120ms`。不达标需记录排查措施与结论。

---

## 2. wrk 基线

| 脚本 | 参数 | QPS | 平均耗时(ms) | P95(ms) | 成功率 | 备注 |
|------|------|-----|---------------|---------|--------|------|
| menu.lua | `-t4 -c100 -d30s` | 待填 | 待填 | 待填 | 待填 |  |
| order_create.lua | `-t2 -c30 -d60s` | 待填 | 待填 | 待填 | 待填 |  |

---

## 3. WebSocket 校验

| 连接数 | 时长(s) | 心跳 P95(ms) | 心跳 P99(ms) | 广播数量 | 广播校验失败 | 备注 |
|--------|---------|--------------|--------------|-----------|----------------|------|
| 200 | 120 | 待填 | 待填 | 待填 | 待填 |  |

---

## 4. 资源占用与数据库指标

| 指标 | 阈值 | 实测 | 备注 |
|------|------|------|------|
| 应用 CPU | ≤ 65% | 待填 | Prometheus `container_cpu_usage_seconds_total` |
| 应用内存 | ≤ 80% | 待填 | Prometheus `container_memory_working_set_bytes` |
| PgBouncer `cl_active` | ≤ 140 | 待填 | `SHOW STATS;` |
| PgBouncer `cl_waiting` | 0 | 待填 |  |
| Redis `used_memory` | < 1GB | 待填 | `info memory` |
| Celery 队列积压 | < 50 | 待填 | Flower / Prometheus |

---

## 5. 瓶颈与优化记录

| 时间 | 环境 | 发现 | 措施 | 结论 |
|------|------|------|------|------|
| 待填 | 待填 | 待填 | 待填 | 待填 |

---

## 6. 回归验证

| 优化项 | 重跑并发 | 指标变化 | 是否达标 | 备注 |
|--------|----------|----------|----------|------|
| 待填 | 待填 | 待填 | 待填 |  |

---

> 提交压测报告时请附上 HTML / JSON 结果存档路径、Git 提交号、环境配置版本（PgBouncer/Redis/Celery）。
