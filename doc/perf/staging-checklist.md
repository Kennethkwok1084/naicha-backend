# Week 0.5 压测环境校验记录

> 负责人：后端-李四；协同：运维-张三  
> 最后更新：填写完成日期

---

## 1. 集群与服务可用性

| 检查项 | 命令/说明 | 结果 | 备注 |
|--------|-----------|------|------|
| K3s 节点状态 | `kubectl get nodes -o wide` | ☐ | 节点均为 `Ready`，包含云端与家庭节点 |
| Staging 命名空间 Pods | `kubectl get pods -n staging` | ☐ | `naicha-api`、`naicha-worker`、`postgres`、`redis`、`celery-beat` 均为 `Running` |
| 健康检查 | `kubectl port-forward svc/naicha-api 8000:80 -n staging` <br> `curl http://127.0.0.1:8000/healthz` | ☐ | 返回 200，响应 < 50ms |
| Celery Worker 心跳 | `kubectl logs deployment/naicha-worker -n staging | tail -n 20` | ☐ | 日志存在 `task.received` / `beat.sync` |
| Redis 连通性 | `redis-cli -h <host> PING` | ☐ | 返回 `PONG`，`info memory` 中 `used_memory_human < 256MB` |
| PostgreSQL 连接 | `psql "postgresql://user:pass@host/db"` | ☐ | `\dt orders* payments* users*` 均存在 |

---

## 2. 脱敏数据快照

| 检查项 | 结果 | 备注 |
|--------|------|------|
| 脱敏快照版本 | ☐ | 记录快照文件名 / 提交号 |
| 历史订单样本 | ☐ | `SELECT COUNT(*) FROM orders;` >= 1,000 |
| 用户样本 | ☐ | `SELECT COUNT(*) FROM users;` >= 50 |
| 商品样本 | ☐ | `SELECT COUNT(*) FROM products;` >= 20 |
| 随机抽样一致性 | ☐ | 对比生产结构（列数/类型一致） |

---

## 3. 预热与依赖

| 检查项 | 结果 | 备注 |
|--------|------|------|
| API 热身请求 | ☐ | `hey -n 50 -c 5 http://127.0.0.1:8000/api/v1/menu` 成功率 100% |
| 订单完整链路 | ☐ | 手工调用 `POST /orders` → `POST /payments/notify/wechat` 成功 |
| WebSocket 连接 | ☐ | `python infra/perf/ws_runner.py --connections 5 --duration 30 --base-url ...` 全部成功 |
| PgBouncer 指标 | ☐ | `SHOW STATS;` 中 `cl_active < 10` |
| Redis SlowLog | ☐ | `SLOWLOG GET 1` 返回空或耗时 < 5ms |

---

## 4. 风险记录

| 风险描述 | 影响 | 应对 | 状态 |
|----------|------|------|------|
| 示例：Redis CPU 偶发飙升 | 场景压测失败 | 降低并发 / 扩容节点 | 处理中 |

---

## 5. 验收结论

- ✅ 环境准备完成 / ☐ 待补充项列举  
- 验收人：填写  
- 下次复核：填写日期
