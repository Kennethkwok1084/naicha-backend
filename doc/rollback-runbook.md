# 生产回滚与应急处理 Runbook

**版本**: V3.0.1  
**Redis 服务器**: 172.21.48.1:6379  
**创建日期**: 2025-10-25  
**维护者**: DevOps Team

---

## 目录
1. [回滚触发条件](#一回滚触发条件)
2. [回滚步骤（快速操作）](#二回滚步骤快速操作)
3. [应急联系方式](#三应急联系方式)
4. [常见故障排查](#四常见故障排查)
5. [故障演练记录](#五故障演练记录)

---

## 一、回滚触发条件

### 1.1 自动回滚触发器（强制）
以下任一条件满足时，**立即**执行回滚流程：

- [ ] **P0 告警持续 > 5 分钟**
  - `HighOrderCreateErrorRate` (错误率 > 0.5%)
  - `HighPaymentCallbackErrorRate` (错误率 > 0.5%)
  - `RedisDown` (Redis 服务宕机)

- [ ] **数据完整性异常**
  - 发现重复扣款（同一订单多次支付成功）
  - 发现库存超卖（负库存或订单商品数量 > 库存）
  - 发现订单丢失（支付成功但无订单记录）

- [ ] **系统资源耗尽**
  - DB 连接池耗尽持续 > 3 分钟
  - 应用 OOM (Out of Memory) 重启 > 3 次/10min
  - CPU 使用率持续 > 95% 超过 5 分钟

### 1.2 人工回滚判断（建议）
以下情况建议人工评估后执行回滚：

- P1 告警持续 > 15 分钟且无明确原因
- 用户投诉激增（> 10 例/10min）
- 第三方依赖服务异常（微信支付/打印机）但短期无法恢复

---

## 二、回滚步骤（快速操作）

### 2.1 Kubernetes 环境回滚

#### Step 1: 立即停止流量导入 (1 分钟内)
```bash
# 将流量导向旧版本 Pod
kubectl set image deployment/naicha-backend \
  app=naicha-backend:<previous_tag> \
  -n production

# 或者快速回滚到上一个 revision
kubectl rollout undo deployment/naicha-backend -n production

# 监控回滚状态
kubectl rollout status deployment/naicha-backend -n production
```

#### Step 2: 验证回滚成功 (2 分钟内)
```bash
# 检查 Pod 状态
kubectl get pods -n production -l app=naicha-backend

# 检查日志（确认旧版本启动）
kubectl logs -n production -l app=naicha-backend --tail=50

# 快速健康检查
curl -f http://<service_url>/api/v1/system/health || echo "❌ 健康检查失败"
```

#### Step 3: 数据库迁移回滚（如需要）
```bash
# 如果 V3.0.1 的迁移导致问题，回滚到上一个版本
# ⚠️ 警告: 迁移回滚可能导致数据丢失，务必先备份数据库

# 进入应用 Pod
kubectl exec -it -n production <pod_name> -- bash

# 查看当前迁移版本
alembic current
# 输出: 20251024_0002 (head)

# 回滚到上一个版本
alembic downgrade -1

# 或者回滚到指定版本
alembic downgrade 20251022_0003

# 验证回滚成功
alembic current
```

### 2.2 Docker Compose 环境回滚

#### Step 1: 停止当前服务
```bash
cd /path/to/naicha-backend
docker compose -f infra/docker/docker-compose.yml down
```

#### Step 2: 切换到旧版本镜像
```bash
# 修改 docker-compose.yml 或使用环境变量
export NAICHA_BACKEND_VERSION=<previous_tag>

# 或者直接 checkout 到上一个 Git Tag
git checkout v3.0.0  # 假设回滚到 V3.0.0

# 重新构建并启动
docker compose -f infra/docker/docker-compose.yml up -d --build
```

#### Step 3: 验证服务恢复
```bash
# 检查容器状态
docker compose -f infra/docker/docker-compose.yml ps

# 检查日志
docker compose -f infra/docker/docker-compose.yml logs -f app

# 健康检查
curl -f http://localhost:8000/api/v1/system/health
```

### 2.3 数据库迁移回滚风险评估

| 迁移版本 | 回滚风险 | 数据丢失风险 | 建议操作 |
|---------|---------|-------------|---------|
| `20251024_0002` (stock_quantity) | 🟢 低 | 🟡 中 | 回滚前导出 `products` 和 `spec_options` 表的 `stock_quantity` 字段数据 |
| `20251024_0001` (print_jobs unique) | 🟡 中 | 🟢 低 | 确认无重复 `order_id` 后可安全回滚 |

**回滚前强制检查**:
```sql
-- 检查是否有依赖新字段的数据
SELECT COUNT(*) FROM products WHERE stock_quantity IS NOT NULL AND stock_quantity != 0;
SELECT COUNT(*) FROM spec_options WHERE stock_quantity IS NOT NULL AND stock_quantity != 0;

-- 如果返回值 > 0，回滚会导致这些库存数据丢失
-- 必须先手动备份数据！
```

---

## 三、应急联系方式

### 3.1 On-call 轮值表

| 时间段 | 角色 | 姓名 | 手机 | 微信/钉钉 |
|--------|------|------|------|-----------|
| 工作日 09:00-18:00 | 后端开发 | ____________ | ____________ | ____________ |
| 工作日 18:00-09:00 | 后端 On-call | ____________ | ____________ | ____________ |
| 周末/节假日 | 运维 On-call | ____________ | ____________ | ____________ |
| 紧急联系人 | 技术负责人 | ____________ | ____________ | ____________ |

### 3.2 应急升级路径

1. **L1 响应** (5 分钟内): On-call 工程师确认告警，初步排查
2. **L2 响应** (15 分钟内): 如果 L1 无法解决，升级到技术负责人
3. **L3 响应** (30 分钟内): 如果涉及业务决策（如全面回滚），通知产品/业务负责人

### 3.3 外部依赖联系方式

| 服务商 | 服务内容 | 联系方式 | 备注 |
|--------|---------|---------|------|
| 微信支付 | 支付 API | 400-xxx-xxxx | 工单系统: https://... |
| 云服务商 | 数据库/Redis | 400-xxx-xxxx | 紧急工单优先级: P0 |
| 打印机厂商 | 打印 Webhook | ____________ | ____________ |

---

## 四、常见故障排查

### 4.1 分布式锁获取失败 (P0-5)

**症状**:
- Prometheus 指标: `payment_match_attempt_total{result="lock_failed"}` 激增
- 日志: `distributed_lock.client_unavailable` 或 `distributed_lock.acquisition_failed`
- API 返回: 409 Conflict (Concurrent match request detected)

**排查步骤**:
```bash
# 1. 检查 Redis 连通性
redis-cli -h 172.21.48.1 PING
# 应返回: PONG

# 2. 检查 Redis 延迟
redis-cli -h 172.21.48.1 --latency
# 应 < 5ms

# 3. 检查 Redis 内存使用
redis-cli -h 172.21.48.1 INFO memory | grep used_memory_human

# 4. 查看当前锁状态
redis-cli -h 172.21.48.1 KEYS "payment_match:*"
# 如果有大量过期未释放的锁，手动清理:
redis-cli -h 172.21.48.1 DEL <lock_key>
```

**应急处理**:
- 如果 Redis 不可用: 重启 Redis 服务（注意：会清空内存数据，确保 AOF 持久化开启）
- 如果并发冲突过高: 临时降低静态码匹配频率（前端限流或排队）

---

### 4.2 菜单缓存版本同步失败 (异步化)

**症状**:
- Prometheus 指标: `menu_cache_version_read_failed_total` 持续增长
- 日志: `menu.cache.version_read_failed`
- 用户体验: 菜单更新延迟或不一致

**排查步骤**:
```bash
# 1. 检查 Redis menu:version 键
redis-cli -h 172.21.48.1 GET menu:version
# 应返回一个整数版本号

# 2. 手动递增版本号触发全局刷新
redis-cli -h 172.21.48.1 INCR menu:version

# 3. 检查应用日志
kubectl logs -n production -l app=naicha-backend | grep "menu.cache"
```

**应急处理**:
- 短期: 清除 Redis `menu:version` 键，强制应用使用 TTL 缓存
  ```bash
  redis-cli -h 172.21.48.1 DEL menu:version
  ```
- 长期: 修复 Redis 连接问题或增加版本同步重试逻辑

---

### 4.3 数据库连接池耗尽 (P0-7)

**症状**:
- Prometheus 指标: `db_pool_connections_used / (db_pool_size + db_pool_max_overflow) > 0.85`
- 日志: `TimeoutError: QueuePool limit of size ... overflow ... reached, connection timed out`
- API 返回: 500 Internal Server Error

**排查步骤**:
```bash
# 1. 检查数据库活跃连接数
psql $DATABASE_URL -c "
SELECT count(*), state FROM pg_stat_activity 
WHERE datname='<your_db_name>' 
GROUP BY state;
"

# 2. 查找长时间运行的查询
psql $DATABASE_URL -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 seconds'
ORDER BY duration DESC;
"

# 3. 终止异常长时间的查询（谨慎操作）
psql $DATABASE_URL -c "SELECT pg_terminate_backend(<pid>);"
```

**应急处理**:
- 临时扩容: 修改 `app/db/session.py` 的 `pool_size` 和 `max_overflow`（需要重启应用）
- 根本解决: 优化慢查询，添加索引，或拆分长事务

---

### 4.4 打印任务重试耗尽 (P1-7)

**症状**:
- Prometheus 指标: `print_job_retry_exhausted_total` 增长
- 日志: `print_job.retry_limit_reached`
- 用户投诉: 未收到打印小票

**排查步骤**:
```bash
# 1. 检查打印队列积压
redis-cli -h 172.21.48.1 LLEN celery:queue:print_jobs

# 2. 查看失败的打印任务
psql $DATABASE_URL -c "
SELECT job_id, order_id, status, try_count, error_message 
FROM print_jobs 
WHERE status = 'failed' AND try_count >= 5 
ORDER BY created_at DESC LIMIT 10;
"

# 3. 测试打印机 Webhook 连通性
curl -X POST $PRINTER_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

**应急处理**:
- 打印机离线: 通知商户检查打印机网络/电源
- Webhook 故障: 临时禁用打印功能或手动重发任务
  ```bash
  # 手动触发重试（在应用容器内）
  python -c "
  from app.workers.print_jobs import execute_print_job
  execute_print_job(<job_id>)
  "
  ```

---

### 4.5 限流误伤（P0-6）

**症状**:
- Prometheus 指标: `rate_limiter_blocked_requests_total` 激增
- 用户投诉: 频繁收到 429 Too Many Requests
- API 返回: 429 (Rate limit exceeded)

**排查步骤**:
```bash
# 1. 检查当前限流配置
echo $RATE_LIMIT_DEFAULT_LIMITS
# 应输出: ["300/minute"]

# 2. 查看被限流的 IP 地址
kubectl logs -n production -l app=naicha-backend | grep "429" | awk '{print $1}' | sort | uniq -c | sort -rn

# 3. 判断是否为恶意流量
# 如果同一 IP 短时间内大量请求，可能是攻击或爬虫
```

**应急处理**:
- 合法用户误伤: 临时提高限流阈值（需重启应用）
  ```bash
  export RATE_LIMIT_DEFAULT_LIMITS='["600/minute"]'
  kubectl rollout restart deployment/naicha-backend -n production
  ```
- 恶意流量: 在 Nginx/云WAF 层面封禁 IP

---

## 五、故障演练记录

### 5.1 Redis 故障演练（Staging）

**演练日期**: ____________  
**演练人**: ____________  
**演练结果**: [ ] 通过 / [ ] 失败

**演练步骤**:
1. 在 Staging 环境执行:
   ```bash
   cd /path/to/naicha-backend/infra/perf
   ./redis_fault_drill.sh block
   ```
2. 观察日志和指标（持续 5 分钟）
3. 恢复 Redis 连接:
   ```bash
   ./redis_fault_drill.sh unblock
   ```
4. 验证系统恢复正常

**观察结果**:
- [ ] 日志中出现 `distributed_lock.client_unavailable`
- [ ] 日志中出现 `menu.cache.version_read_failed`
- [ ] 静态码匹配返回 409
- [ ] 菜单读取仍可用 (TTL 缓存)
- [ ] 恢复后 1 分钟内系统正常

**改进建议**: ____________

---

### 5.2 数据库连接池耗尽演练（Staging）

**演练日期**: ____________  
**演练人**: ____________  
**演练结果**: [ ] 通过 / [ ] 失败

**演练步骤**:
1. 临时降低连接池大小触发压力:
   ```python
   # 修改 app/db/session.py
   pool_size=5,  # 降低到 5
   max_overflow=5,  # 降低到 5
   ```
2. 运行 50 并发压测
3. 观察连接池耗尽告警和错误日志
4. 恢复配置并重启应用

**观察结果**:
- [ ] Prometheus 告警触发: `DatabaseConnectionPoolNearLimit`
- [ ] 日志中出现连接超时错误
- [ ] API 返回 500 错误
- [ ] 恢复后 2 分钟内系统正常

**改进建议**: ____________

---

## 六、附录

### 6.1 快速命令清单

```bash
# === Kubernetes 快速回滚 ===
kubectl rollout undo deployment/naicha-backend -n production
kubectl rollout status deployment/naicha-backend -n production

# === Redis 连通性检查 ===
redis-cli -h 172.21.48.1 PING

# === 数据库迁移状态 ===
kubectl exec -it -n production <pod> -- alembic current

# === 强制清理菜单缓存 ===
redis-cli -h 172.21.48.1 DEL menu:version

# === 查看实时错误日志 ===
kubectl logs -n production -l app=naicha-backend -f | grep ERROR

# === 查看 Prometheus 告警 ===
curl http://<prometheus_url>/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'
```

### 6.2 回滚决策流程图

```
告警触发
    ↓
是否为 P0 告警？
    ├─ 是 → 立即执行回滚（无需审批）
    └─ 否 → 是否持续 > 15 分钟？
            ├─ 是 → 升级到 L2，评估回滚
            └─ 否 → 继续观察，记录日志
```

---

**文档版本**: V1.0  
**最后更新**: 2025-10-25  
**下次审查**: 2025-11-25
