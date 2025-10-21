# PgBouncer / Redis / Celery 配置对比（Week 0.5）

> 负责人：DBA-赵六  
> 最后更新：填写日期

---

## 摘要

| 组件 | 当前 Staging | 生产现状 | 建议 Week1 目标值 | 性能影响 | 回滚方案 |
|------|--------------|----------|-------------------|----------|----------|
| PgBouncer | `session` 模式，`max_client_conn=100` | 同 staging | `pool_mode=transaction`，`max_client_conn=200`，`default_pool_size=25` | 预计降低活动连接占用 ≥40%，`cl_waiting` 保持 0 | 保留原 `session` 模式并回退连接上限 |
| Redis | `maxmemory=0`，无淘汰策略 | 计划单节点 2GB | `maxmemory=1GB`，`maxmemory-policy=allkeys-lru`，`timeout=300` | 控制内存峰值，命中率期望 ≥90%，避免 OOM 导致 5xx | 恢复为无限制 (`maxmemory=0`) |
| Celery Worker | `concurrency=2`，`prefetch_multiplier=1` | 同 staging | `concurrency=4`，`prefetch_multiplier=4`，`task_acks_late=True` | 提升吞吐（打印/通知）约 2 倍，队列待处理数维持 < 50 | 回退为原 Deployment 环境变量 |

---

## PgBouncer

| 参数 | Staging 当前值 | Week1 目标 | 说明 |
|------|----------------|-----------|------|
| `pool_mode` | `session` | `transaction` | 降低连接占用，便于高并发压测 |
| `max_client_conn` | `100` | `200` | 允许更多客户端连接 |
| `default_pool_size` | `20` | `25` | 匹配数据库 `max_connections=200` |
| `reserve_pool_size` | `0` | `5` | 防止短暂尖峰打满 |
| `server_tls_sslmode` | `prefer` | `prefer` | 无变更 |

**验证步骤**
1. 修改 `config/pgbouncer.ini` 并热重载：`kill -SIGHUP $(pidof pgbouncer)`。
2. 压测 200 并发请求，观察 `SHOW STATS;` 中 `cl_waiting=0`。
3. 采集 `doc/perf-baseline.md` 中 `orders` 请求 P95，目标 ≤ 200ms。

**回滚方案**
- 恢复旧配置文件备份并再次发送 `SIGHUP`。
- 如果仍存在异常，切换应用为直连数据库（更新 DSN）。

---

## Redis

| 参数 | Staging 当前值 | Week1 目标 | 说明 |
|------|----------------|-----------|------|
| `maxmemory` | `0` | `1gb` | 防止 Redis 撑爆节点内存 |
| `maxmemory-policy` | `noeviction` | `allkeys-lru` | 保证热数据留存 |
| `timeout` | `0` | `300` | 长时间空闲连接自动关闭 |
| `tcp-keepalive` | `0` | `60` | 减少僵尸连接 |

**验证步骤**
1. 更新 ConfigMap 并 `kubectl rollout restart statefulset/redis -n staging`。
2. 压测期间监控 `used_memory` < 1GB、`evicted_keys` 不持续增长。
3. 使用 `redis-benchmark -t get,set -c 50 -n 10000`，吞吐 ≥ 20k ops/s。

**回滚方案**
- 恢复 ConfigMap 旧版本并重新发布。
- 如发生大量淘汰，将 `maxmemory=0` 暂停淘汰策略。

---

## Celery Worker

| 参数 | Staging 当前值 | Week1 目标 | 说明 |
|------|----------------|-----------|------|
| `worker_concurrency` | `2` | `4` | 双倍并发处理打印/通知队列 |
| `task_acks_late` | `False` | `True` | 任务执行后才确认，避免丢单 |
| `worker_prefetch_multiplier` | `1` | `4` | 减少空闲 worker 等待 |
| `worker_max_tasks_per_child` | `0` | `100` | 避免内存泄漏 |

**验证步骤**
1. 修改 Deployment 环境变量，运行 `kubectl rollout restart deployment/naicha-worker -n staging`。
2. 使用 `celery -A app.workers inspect stats`，确认 `pool.max-concurrency=4`。
3. 压测订单支付链路时，`task latency P95 ≤ 5s`。

**回滚方案**
- 使用 `kubectl rollout undo deployment/naicha-worker -n staging`。
- 如需要立刻缩容，将 `worker_concurrency=2` 并重启。

---

## 记录与跟踪

- [ ] 已完成配置更新，日期：填写  
- [ ] 已通过压测验证，报告链接：填写  
- [ ] 回滚测试完成（可选）
