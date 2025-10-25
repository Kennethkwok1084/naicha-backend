# 生产环境配置审查清单

**版本**: V3.0.1  
**Redis 服务器**: 172.21.48.1:6379  
**审查日期**: ____________  
**审查人**: ____________

---

## 一、环境变量配置

### 1.1 限流配置 (P0-6)
- [ ] `RATE_LIMIT_DEFAULT_LIMITS` 已设置为 `["300/minute"]`
- [ ] `PERF_DISABLE_HTTP_OVERHEADS` **未设置** 或设置为 `0` (生产必须启用限流)
- [ ] 验证命令:
  ```bash
  # 在生产容器/Pod 中执行
  echo $RATE_LIMIT_DEFAULT_LIMITS  # 应输出: ["300/minute"]
  echo $PERF_DISABLE_HTTP_OVERHEADS  # 应为空或 0
  ```

### 1.2 数据库连接池配置 (P0-7)
- [ ] `DATABASE_POOL_SIZE` 设置为 `20`（可根据并发压测结果调优）
- [ ] `DATABASE_MAX_OVERFLOW` 设置为 `30`
- [ ] 总连接数 ≈ 50，足够覆盖 150 并发场景
- [ ] 验证文件: `app/db/session.py`
  ```python
  pool_size=max(settings.database_pool_size, 1),
  max_overflow=max(settings.database_max_overflow, 0),
  ```

### 1.3 JWT 安全配置 (P1-6)
- [ ] `JWT_EXPIRE_MINUTES` 设置为 `1440` (1 天) 或更短
- [ ] 验证命令:
  ```bash
  echo $JWT_EXPIRE_MINUTES  # 应输出: 1440
  ```
- [ ] 确认 `JWT_SECRET_KEY` 为生产环境独立密钥 (不与 Staging 共享)

### 1.4 Redis 配置
- [ ] `CELERY_BROKER_URL` 指向 `redis://172.21.48.1:6379/0`
- [ ] Redis 服务器已配置 AOF 持久化 (防止 Celery 任务丢失)
  ```bash
  # 在 Redis 服务器上检查
  redis-cli -h 172.21.48.1 CONFIG GET appendonly
  # 应输出: 1) "appendonly" 2) "yes"
  ```
- [ ] Redis 密码已配置 (如果生产环境需要认证)

### 1.5 数据库配置
- [ ] `DATABASE_URL` 指向生产数据库 (不与 Staging 共享)
- [ ] 数据库连接使用 SSL/TLS (生产环境推荐)
- [ ] 数据库用户权限最小化 (仅授予必要的 SELECT/INSERT/UPDATE 权限)

### 1.6 日志与监控
- [ ] `LOG_LEVEL` 设置为 `INFO` (避免 DEBUG 级别日志影响性能)
- [ ] Prometheus metrics 端口已暴露 (默认 `/metrics` 路径)
- [ ] 日志输出格式为 JSON (便于日志聚合)

---

## 二、数据库迁移验证

### 2.1 迁移状态检查
- [ ] 执行迁移检查命令:
  ```bash
  cd /path/to/naicha-backend
  source .venv/bin/activate
  alembic current
  # 应输出: 20251024_0002 (head)
  ```
- [ ] 确认以下迁移已应用:
  - [ ] `20251024_0001`: print_jobs 表 `order_id` 唯一约束
  - [ ] `20251024_0002`: products/spec_options 表 `stock_quantity` 字段

### 2.2 数据完整性验证
- [ ] 运行数据验证查询:
  ```sql
  -- 检查 print_jobs 唯一约束
  SELECT order_id, COUNT(*) FROM print_jobs 
  GROUP BY order_id HAVING COUNT(*) > 1;
  -- 应返回空结果
  
  -- 检查 stock_quantity 字段存在
  SELECT stock_quantity FROM products LIMIT 1;
  SELECT stock_quantity FROM spec_options LIMIT 1;
  ```

---

## 三、功能开关与特性标志

### 3.1 核心功能开关
- [ ] `MULTI_CATEGORY_ENABLED`: 确认是否启用多分类功能
- [ ] `RESERVATION_ENABLED`: 确认是否启用预约功能
- [ ] `WANT_ENABLED`: 确认是否启用"想要"功能
- [ ] `STATIC_QR_MATCH_ENABLED`: 确认静态码匹配是否启用 (默认关闭)

### 3.2 性能开关 (生产环境必须关闭)
- [ ] `PERF_DISABLE_HTTP_OVERHEADS=0` (已在 1.1 确认)
- [ ] `PERF_DISABLE_DB_PROFILER=0` (保留慢查询监控)

---

## 四、依赖服务验证

### 4.1 Redis 连通性测试
- [ ] 从应用服务器测试 Redis 连接:
  ```bash
  redis-cli -h 172.21.48.1 PING
  # 应返回: PONG
  ```
- [ ] 测试分布式锁功能:
  ```bash
  # 在应用容器内执行
  python -c "
  import asyncio
  from app.utils.distributed_lock import distributed_lock
  
  async def test():
      async with distributed_lock('test:lock', timeout=5) as acquired:
          print(f'Lock acquired: {acquired}')
  
  asyncio.run(test())
  "
  # 应输出: Lock acquired: True
  ```

### 4.2 数据库连通性测试
- [ ] 测试数据库连接:
  ```bash
  psql $DATABASE_URL -c "SELECT 1;"
  # 应返回: (1 row)
  ```

### 4.3 第三方服务测试
- [ ] 微信支付 API 可达 (测试环境或生产环境密钥已配置)
- [ ] 打印机 Webhook 可达 (配置 `PRINTER_WEBHOOK_URL`)
- [ ] (可选) 短信/邮件服务可达

---

## 五、安全配置

### 5.1 密钥管理
- [ ] 所有敏感配置通过环境变量或 Secrets 管理 (不在代码中硬编码)
- [ ] `JWT_SECRET_KEY` 长度 >= 32 字符
- [ ] 微信支付密钥 (`WECHAT_PAY_API_V3_KEY`) 已配置且正确

### 5.2 网络安全
- [ ] 生产数据库仅允许应用服务器 IP 访问
- [ ] Redis 仅允许应用服务器 IP 访问 (或使用密码认证)
- [ ] 应用服务器防火墙规则已配置 (仅暴露必要端口)

### 5.3 HTTPS/TLS
- [ ] 生产环境使用 HTTPS (Let's Encrypt 或其他 CA 证书)
- [ ] API 端点禁用 HTTP 访问 (强制跳转到 HTTPS)

---

## 六、监控与告警

### 6.1 Prometheus 指标
- [ ] Prometheus 能抓取应用 `/metrics` 端点
- [ ] 关键指标已暴露:
  - [ ] `order_create_total`, `order_create_errors_total`
  - [ ] `payment_callback_total`, `payment_callback_latency_ms`
  - [ ] `payment_match_attempt_total`
  - [ ] `db_pool_connections_used`
  - [ ] `menu_cache_hit_total`, `menu_cache_version_read_failed_total`
  - [ ] `print_job_retry_exhausted_total`

### 6.2 Grafana Dashboard
- [ ] 导入 `infra/k3s/grafana-dashboard.json`
- [ ] Dashboard 能正常显示数据
- [ ] 关键面板:
  - [ ] 业务核心指标 (QPS, 错误率)
  - [ ] 延迟分析 (P50/P95/P99)
  - [ ] 并发安全监控 (锁失败, DB 连接池)
  - [ ] Redis 监控 (命令延迟, 菜单缓存)

### 6.3 Prometheus 告警规则
- [ ] 应用告警规则: `infra/k3s/prometheus-rules.yaml`
- [ ] 测试告警触发:
  ```bash
  # 模拟高错误率 (在 Staging 环境)
  # 观察告警是否在 5 分钟内触发
  ```
- [ ] 告警接收渠道已配置 (钉钉/Slack/PagerDuty)

---

## 七、备份与恢复

### 7.1 数据库备份
- [ ] 数据库自动备份已配置 (每日全量 + 增量)
- [ ] 备份保留策略: ≥ 7 天
- [ ] 备份恢复流程已演练 (至少 1 次)

### 7.2 代码版本管理
- [ ] 生产部署使用 Git Tag (例如 `v3.0.1`)
- [ ] 部署镜像打 Tag (例如 `naicha-backend:v3.0.1`)
- [ ] Helm Chart / K8s Manifest 版本化

---

## 八、压测结果确认

### 8.1 150 并发压测
- [ ] 压测已完成 (使用 `infra/perf/run_150_concurrent_test.sh`)
- [ ] 压测结果符合目标:
  - [ ] 错误率 < 0.5%
  - [ ] P99 延迟 < 1000ms (下单与支付回调)
  - [ ] 无 DB 连接池耗尽
  - [ ] 无 Redis 连接超时
- [ ] 压测报告已归档: `perf_results/150u_<timestamp>.html`

### 8.2 Redis 故障演练
- [ ] 故障演练已完成 (使用 `infra/perf/redis_fault_drill.sh`)
- [ ] 观察到预期降级行为:
  - [ ] 日志中出现 `distributed_lock.client_unavailable`
  - [ ] 日志中出现 `menu.cache.version_read_failed`
  - [ ] 静态码匹配返回 409 (lock acquisition failed)
  - [ ] 菜单读取仍可用 (TTL 缓存降级)
- [ ] 恢复后系统正常

---

## 九、上线前最终检查

### 9.1 代码审查
- [ ] P0 修复代码已合并到 master 分支
- [ ] 所有测试通过: `make test` (128 passed, 5 skipped)
- [ ] 代码风格检查通过: `make lint` (仅剩余中文字符告警)

### 9.2 文档更新
- [ ] README.md 已更新 V3.0.1 变更日志
- [ ] API 文档已更新 (`doc/api.md`)
- [ ] Runbook 已更新故障排查步骤 (见 `doc/rollback-runbook.md`)

### 9.3 团队准备
- [ ] On-call 轮值表已更新
- [ ] 应急联系方式已确认 (技术、产品、运营)
- [ ] 回滚计划已评审并同步给团队

---

## 十、签名确认

| 角色 | 姓名 | 签名 | 日期 |
|------|------|------|------|
| 开发负责人 | ____________ | ____________ | ____________ |
| 测试负责人 | ____________ | ____________ | ____________ |
| 运维负责人 | ____________ | ____________ | ____________ |
| 产品负责人 | ____________ | ____________ | ____________ |

---

## 附录：快速检查命令

### 一键环境变量检查
```bash
#!/bin/bash
echo "=== 限流配置 ==="
echo "RATE_LIMIT_DEFAULT_LIMITS: $RATE_LIMIT_DEFAULT_LIMITS"
echo "PERF_DISABLE_HTTP_OVERHEADS: $PERF_DISABLE_HTTP_OVERHEADS"
echo ""
echo "=== JWT 配置 ==="
echo "JWT_EXPIRE_MINUTES: $JWT_EXPIRE_MINUTES"
echo ""
echo "=== Redis 配置 ==="
echo "CELERY_BROKER_URL: $CELERY_BROKER_URL"
redis-cli -h 172.21.48.1 PING 2>/dev/null && echo "Redis: ✅ 可达" || echo "Redis: ❌ 不可达"
echo ""
echo "=== 数据库配置 ==="
echo "DATABASE_URL: ${DATABASE_URL%%@*}@***"  # 隐藏密码
echo ""
echo "=== 数据库迁移状态 ==="
cd /path/to/naicha-backend && alembic current
```

### Prometheus 指标抽查
```bash
# 检查关键指标是否暴露
curl -s http://localhost:8000/metrics | grep -E "order_create_total|payment_callback_total|db_pool_connections_used|payment_match_attempt_total"
```
