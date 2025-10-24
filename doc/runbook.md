# 运维 Runbook（M4-M6 新增功能 + 生产部署检查清单）

## 目录
1. [🔒 生产部署前检查清单](#生产部署前检查清单)
2. [监控指标与告警阈值](#监控指标与告警阈值)
3. [POS 快速建单故障排查](#pos-快速建单故障排查)
4. [静态码支付匹配故障排查](#静态码支付匹配故障排查)
5. [数据看板异常排查](#数据看板异常排查)
6. [预约提醒任务排查](#预约提醒任务排查)
7. [售罄/库存刷新排查](#售罄库存刷新排查)
8. [「想要」统计排查](#想要统计排查)
9. [每日对账任务排查](#每日对账任务排查)
10. [自动降级演练流程](#自动降级演练流程)

---

## 🔒 生产部署前检查清单

**重要提示**：以下配置在性能测试时被临时修改，生产部署前必须逐项检查并修复。

### 1. API 限流器（致命风险 🚨）

**检查项**：
- [ ] `app/main.py` 中 `init_rate_limiter(app)` 已取消注释
- [ ] `app/api/routes/payments.py` 中 `@limiter.limit("18000/minute;300/second")` 已取消注释
- [ ] `app/api/routes/orders/__init__.py` 中 `@limiter.limit("3000/minute")` 已取消注释
- [ ] 所有其他路由的限流装饰器已恢复

**验证方法**：
```bash
# grep 检查是否有注释掉的限流器
grep -r "# init_rate_limiter\|# @limiter.limit" app/

# 预期：无输出（所有限流器已启用）
```

**风险说明**：无限流保护会导致服务在 DDoS 攻击或爬虫扫描时瞬间崩溃。

---

### 2. JWT 有效期（高危风险 😱）

**检查项**：
- [ ] `.env` 中设置 `JWT_EXPIRE_MINUTES=60`（1 小时）或 `JWT_EXPIRE_MINUTES=1440`（1 天）
- [ ] 确认不使用默认值 43200 分钟（30 天）

**验证方法**：
```bash
# 检查 .env 文件
grep JWT_EXPIRE_MINUTES .env

# 预期输出示例：
# JWT_EXPIRE_MINUTES=60
```

**风险说明**：30 天有效期严重违反安全设计，Token 泄露后攻击窗口过长。

---

### 3. 数据库连接池（高危风险 💣）

**检查项**：
- [ ] `app/db/session.py` 中 `pool_size` 和 `max_overflow` 已根据服务器资源调整

**推荐配置**：

| 服务器配置 | 并发需求 | pool_size | max_overflow | 总连接数 |
|-----------|---------|-----------|--------------|---------|
| 2c2g | 10 并发 | 10 | 10 | 20 |
| 2c4g | 50 并发 | 30 | 20 | 50 |
| 4c8g | 100 并发 | 50 | 30 | 80 |

**当前配置**（仅用于压测）：
```python
pool_size=200, max_overflow=250  # 总 450 连接，会 OOM！
```

**验证方法**：
```bash
# 检查代码
grep -A 5 "create_async_engine" app/db/session.py | grep pool_size

# 部署后检查实际连接数
PGPASSWORD=$DB_PASS psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='naicha';"
```

**风险说明**：450 连接会占用 4.5GB+ 内存，2c2g 服务器会因 OOM 崩溃。

---

### 4. 环境配置（配置风险 😵）

**检查项**：
- [ ] `APP_ENV=prod`（不是 dev）
- [ ] `CELERY_BROKER_URL=redis://redis:6379/0`（不是 localhost）
- [ ] `WS_BROADCAST_URL=redis://redis:6379/0`（不是 localhost）
- [ ] `ALLOWED_ORIGINS` 包含实际域名（不仅是 localhost）

**`.env` 示例**：
```bash
# 环境
APP_ENV=prod

# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/naicha

# Redis（Docker Compose 中服务名）
CELERY_BROKER_URL=redis://redis:6379/0
WS_BROADCAST_URL=redis://redis:6379/0

# CORS（逗号分隔，无空格）
ALLOWED_ORIGINS=https://miniapp.example.com,https://admin.example.com

# JWT
JWT_EXPIRE_MINUTES=60
JWT_SECRET_KEY=生产环境使用强随机密钥

# 日志
LOG_LEVEL=INFO
```

**验证方法**：
```bash
# 检查关键配置
grep -E "^(APP_ENV|CELERY_BROKER_URL|ALLOWED_ORIGINS|JWT_EXPIRE_MINUTES)=" .env
```

**风险说明**：
- `localhost` 配置在 Docker 容器中无法工作
- CORS 不正确会导致前端无法访问 API
- 开发模式会泄露敏感信息（SQL 日志、Swagger）

---

### 5. Docker Compose 生产配置（部署风险 😥）

**检查项**：
- [ ] `docker-compose.prod.yml` 已创建
- [ ] 包含 5 个服务：api、postgres、redis、worker、beat
- [ ] API 服务使用 Gunicorn（不是 `uvicorn --reload`）
- [ ] 不挂载源码（使用构建好的镜像）
- [ ] 所有服务配置了 `restart: unless-stopped`
- [ ] 数据库和 Redis 配置了持久化卷

**最小化 `docker-compose.prod.yml` 示例**：
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: naicha
      POSTGRES_USER: user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

  api:
    build:
      context: .
      dockerfile: infra/docker/app.Dockerfile
    restart: unless-stopped
    command: gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    env_file: .env

  worker:
    build:
      context: .
      dockerfile: infra/docker/app.Dockerfile
    restart: unless-stopped
    command: celery -A app.workers.celery_app worker -l info
    depends_on:
      - postgres
      - redis
    env_file: .env

  beat:
    build:
      context: .
      dockerfile: infra/docker/app.Dockerfile
    restart: unless-stopped
    command: celery -A app.workers.celery_app beat -l info
    depends_on:
      - redis
    env_file: .env

volumes:
  postgres_data:
  redis_data:
```

**验证方法**：
```bash
# 检查服务定义
docker-compose -f docker-compose.prod.yml config

# 测试启动
docker-compose -f docker-compose.prod.yml up -d

# 检查所有服务运行
docker-compose -f docker-compose.prod.yml ps

# 检查 Celery 任务
docker-compose -f docker-compose.prod.yml logs worker | grep "ready"
docker-compose -f docker-compose.prod.yml logs beat | grep "Scheduler"
```

**风险说明**：
- 缺少 worker/beat 会导致打印、预约提醒等后台任务失败
- 使用开发配置会有性能问题和数据丢失风险

---

### 6. 菜单缓存限制（扩展性风险 ⚠️）

**检查项**：
- [ ] 确认部署为**单实例**（不使用 `--scale api=2`）
- [ ] 在文档中注明"当前仅支持单实例部署"

**当前限制**：
- `app/services/menu.py` 使用内存缓存（全局变量 `_MENU_CACHE`）
- 多实例部署会导致缓存不一致

**未来改造**（记录到技术债务）：
- 迁移到 Redis 缓存
- 支持多实例共享缓存

**验证方法**：
```bash
# 检查运行实例数
docker-compose -f docker-compose.prod.yml ps api | wc -l

# 预期：2（标题行 + 1 个实例）
```

---

### 7. 最终验收测试

**功能测试**：
- [ ] 限流测试：快速请求触发 429 错误
  ```bash
  for i in {1..100}; do curl http://api.example.com/api/v1/menu & done
  # 预期：部分请求返回 429 Too Many Requests
  ```

- [ ] JWT 过期测试：Token 在配置时间后失效
  ```bash
  # 获取 Token
  TOKEN=$(curl -X POST http://api.example.com/api/v1/users/login ...)
  
  # 等待过期时间后测试
  sleep 3700  # 如果 JWT_EXPIRE_MINUTES=60
  curl -H "Authorization: Bearer $TOKEN" http://api.example.com/api/v1/me/profile
  # 预期：401 Unauthorized
  ```

- [ ] Celery 任务测试：
  ```bash
  # 检查打印任务
  docker-compose -f docker-compose.prod.yml logs worker | grep "print_job"
  
  # 检查预约提醒
  docker-compose -f docker-compose.prod.yml logs beat | grep "reservation"

  # Redis 锁状态（存在表示有实例执行中）
  redis-cli -u "$CELERY_BROKER_URL" GET celery:lock:print_job_recovery
  ```

- [ ] CORS 测试：前端可正常访问
  ```bash
  curl -H "Origin: https://miniapp.example.com" \
       -H "Access-Control-Request-Method: POST" \
       -X OPTIONS http://api.example.com/api/v1/orders
  # 预期：返回 Access-Control-Allow-Origin 头
  ```

**性能测试**：
- [ ] 连接池监控：实际连接数 < 配置上限
  ```sql
  SELECT count(*), state FROM pg_stat_activity 
  WHERE datname='naicha' GROUP BY state;
  ```

- [ ] 内存监控：应用内存使用 < 服务器容量 80%
  ```bash
  docker stats --no-stream
  ```

**安全测试**：
- [ ] 确认 `/docs` 和 `/redoc` 在生产环境关闭
- [ ] 确认敏感信息不在日志中暴露
- [ ] 确认数据库密码不是默认值

---

## 监控指标与告警阈值

| 指标 | 说明 | 建议阈值 / 告警条件 |
|------|------|---------------------|
| `admin_order_created_total{result=*}` | POS 建单总量与结果 | 10 分钟内 `result="error"` 占比 > 5% 告警 |
| `admin_order_create_latency_ms` | POS 建单延迟直方图 | P95 > 200ms 告警 |
| `payment_match_attempt_total{result=*}` | 静态码匹配尝试结果 | 5 分钟内 `result="matched"` 低于 1/min 告警；`result="conflict"` > 10% 告警 |
| `loyalty_points_awarded_total` | 积分发放计数 | 5 分钟内无积分发放 + 销量正常 ⇒ 告警 |
| `coupon_issued_total{reason="loyalty10"}` | 满 10 积分发券数量 | 30 分钟内连续为 0 + 日活≥100 ⇒ 告警 |
| `admin_dashboard_query_latency_ms` | 看板查询延迟 | P95 > 120ms 告警 / P99 > 300ms 严重告警 |
| `print_job.enqueue_failed`（结构化日志） | 打印入队失败 | 1 分钟内多次出现 ⇒ 需排查 Celery/Redis |
| `reservation_reminder_total` / `reservation_activated_total` | 预约提醒/入列次数 | 5 分钟内为 0 且当日预约>0 ⇒ 告警；连续失败需排查任务日志 |
| `celery_task_runtime_seconds{task="run_daily_reconciliation"}` | 对账任务执行时长 | 持续 >60s 告警；>120s 升级 |
| `reconciliation_diff_count{type=*}` | 当日对账差异数量 | `type=unmatched_payments` 连续两日 >0 ⇒ 告警 |
| `want_event_total`（规划） / `admin_want_stats_latency_ms` | 「想要」事件与统计延迟 | 暂无告警，M6 绑定面板 |

> **提示**：告警打点后请同步在 Grafana 面板添加对应 Panel 与 Alert Rule，详见监控配置文件。

---

## POS 快速建单故障排查

1. **确认请求参数**
   - 检查负载均衡 / 网关日志，确认 `X-Idempotency-Key` 是否传递、管理员角色是否正确。
2. **查看审计日志**
   ```sql
   SELECT *
   FROM audit_logs
   WHERE action = 'pos.order.create'
   ORDER BY created_at DESC
   LIMIT 20;
   ```
   - 重点关注 `after_json` 中的 `payment_channel`、`payment_status`。
3. **检查库存 / 商品状态**
   ```sql
   SELECT product_id, status, inventory_status
   FROM products
   WHERE product_id IN (...);
   ```
   若状态为 inactive / sold_out，会返回 409。
4. **打印任务确认**
   ```sql
   SELECT *
   FROM print_jobs
   WHERE order_id = :order_id
   ORDER BY created_at DESC;
   ```
   - `status = failed` 且 `last_error` 存在 ⇒ 需要人工重试或排查打印服务。
5. **缓存刷新**
   - POS 下单成功后会刷新看板缓存，若看板未更新，请检查 Dashboard 缓存逻辑（见下一节）。

---

## 静态码支付匹配故障排查

1. **查看 API 响应**
   - 409 `payment.match_ambiguous`：响应体中包含 `candidates`，需要人工确认后携带 `force_order_id` 再次请求。
   - 409 `payment.match_conflict`：通常是金额不一致或订单已付款。
2. **检查支付记录状态**
   ```sql
   SELECT *
   FROM payment_records
   WHERE qr_session_id = :qr_session_id
      OR txn_id = :transaction_id
   ORDER BY created_at DESC;
   ```
   - `match_status` 应为 `unmatched` 才能继续匹配。
3. **核对订单状态**
   ```sql
   SELECT order_id, order_number, payment_status, status, total_price, updated_at
   FROM orders
   WHERE payment_status = 'pending'
   ORDER BY updated_at DESC
   LIMIT 50;
   ```
   - 确保金额与支付记录 `amount` 精确一致（两位小数）。
4. **打印任务与通知**
   - 成功匹配会创建/重置打印任务并推送 WebSocket，如未触发，需检查 Celery 队列或 WS 链路。
5. **审计追踪**
   ```sql
   SELECT *
   FROM audit_logs
   WHERE action = 'admin.payment.match'
   ORDER BY created_at DESC
   LIMIT 20;
   ```
   - 可检索匹配历史、操作管理员、trace_id 等上下文。

---

## 数据看板异常排查

1. **确认缓存状态**
   - Dashboard 有 60s 内存缓存；可调用 `POST /api/v1/admin/orders`/`POST /api/v1/admin/payments/match` 后立即刷新，或通过 shell 调用：
     ```python
     from app.services.dashboard import DashboardService
     await DashboardService(session).invalidate_cache()
     ```
2. **检查聚合 SQL 执行**
   ```sql
   EXPLAIN ANALYZE
   SELECT COUNT(order_id), SUM(total_price)
   FROM orders
   WHERE payment_status = 'paid'
     AND updated_at BETWEEN :start AND :end;
   ```
   - 若耗时 >100ms，可考虑增补索引或引入物化视图。
3. **查看慢查询**
   - Postgres: `pg_stat_statements` 或 APM 监控；重点关注 `orders` / `order_items` 聚合查询。
4. **核对数据延迟**
   - `summary.gross_sales` 与 `payment_match`/`pos` 成功总额不一致时，需检查看板缓存是否刷新或有未完成事务。
5. **趋势 / Top5 缺失**
   - 若 `trend` 或 `top_products` 为空，请确认测试数据是否满足时间窗口；手动执行查询验证是否有结果。
6. **Prometheus 指标**
   - `admin_dashboard_query_latency_ms` 长期大于 200ms ⇒ 关注数据库性能或增加 Redis 缓存。

---

> 本 Runbook 仅涵盖 M4 新增功能。后续若扩展 Grafana 面板、Prometheus 告警或网络探测 CronJob，请同步更新本文件的相关章节。

---

## 预约提醒任务排查

1. **确认 Celery 任务状态**
   - 日志关键字：`reservation.reminder_sent` / `reservation.activated_orders`
   - 指标：`reservation_reminder_total`、`reservation_activated_total`
2. **验证待执行数据**
   ```sql
   SELECT order_id, scheduled_at, reminder_sent_at, status, payment_status
   FROM orders
   WHERE is_scheduled = TRUE
     AND scheduled_at BETWEEN now() - interval '1 day' AND now() + interval '1 day';
   ```
   - `payment_status != 'paid'` ⇒ 不会提醒/入列，需要先确认支付
3. **检查分布式锁**
   ```bash
   redis-cli -u "$CELERY_BROKER_URL" GET celery:lock:reservation_send_reminders
   redis-cli -u "$CELERY_BROKER_URL" GET celery:lock:reservation_activate_due_orders
   ```
   - 返回值存在 ⇒ 某实例正在运行；若锁长期不消失且日志无进展，可 `DEL` 后手动重跑任务
4. **检查任务堆积**
   ```sql
   SELECT *
   FROM celery_taskmeta
   WHERE task_name LIKE 'app.workers.tasks.reservation_%'
   ORDER BY date_done DESC
   LIMIT 20;
   ```
5. **常见问题**
   - 调整营业时间：更新 `shop_profile.open_hours_json` 后立即生效
   - 提醒未发送：确认 `reservation_reminder_minutes` 是否 >=5；过小会被验证拒绝
6. **恢复步骤**
   - 手动执行：`celery -A app.workers.celery_app call app.workers.tasks.reservation_send_reminders`
   - 若个别订单延迟，可人工将 `reminder_sent_at` 置空并重跑任务

---

## 售罄库存刷新排查

1. **确认审计日志**
   ```sql
   SELECT created_at, actor_admin_id, target_id, before_json, after_json
   FROM audit_logs
   WHERE action IN ('admin.inventory.product.update','admin.inventory.spec_option.update')
   ORDER BY created_at DESC
   LIMIT 20;
   ```
2. **检查菜单缓存**
   - 日志：`menu.cache.hit` / `menu.cache.miss`
   - 多实例部署下通过 Redis 版本号即时失效；Redis 不可用时仍回退到 TTL=240s（最长 4 分钟延迟）
3. **手动刷新**
   ```python
   from app.services.menu import invalidate_menu_cache
   invalidate_menu_cache()
   ```
4. **常见问题**
   - 产品未绑定分类 ⇒ `/menu` 落到 `uncategorized_products`
   - 规格库存变化未同步 ⇒ 确认 `spec_options.inventory_status` 触发事件监听

---

## 「想要」统计排查

1. **限流命中**
   - 日志：`want.rate_limited`（若新增）；HTTP 429
   - 检查 SlowAPI 头 `X-RateLimit-Remaining`
2. **查询事件明细**
   ```sql
   SELECT product_id, user_id, ip_hash, created_at
   FROM want_events
   WHERE created_at >= now() - interval '1 day'
   ORDER BY created_at DESC
   LIMIT 50;
   ```
3. **统计校验**
   ```sql
   SELECT date_trunc('day', created_at) AS day, COUNT(*)
   FROM want_events
   WHERE product_id = :pid AND created_at >= now() - interval '30 days'
   GROUP BY 1
   ORDER BY 1;
   ```
4. **Feature Flag**
   - `WANT_ENABLED=false` 时接口返回 503；确认配置文件或环境变量
5. **恢复建议**
   - 批量修补：如需补写数据，可导入历史日志再调用 `WantService.record_want`（注意限流）

---

## 每日对账任务排查

### 对账脚本使用

**脚本路径**：`scripts/reconcile_payments.py`

**功能**：封装 `ReconciliationService`，支持指定日期、CSV 导出、差异告警，用于日常运维或 CI 验收。

**基本用法**：

```bash
# 1. 对上一自然日对账（默认行为）
python scripts/reconcile_payments.py

# 2. 指定日期对账（格式 YYYY-MM-DD）
python scripts/reconcile_payments.py --date 2025-10-22

# 3. 强制导出 CSV（覆盖 RECONCILIATION_CSV_ENABLED 配置）
python scripts/reconcile_payments.py --csv

# 4. 严格模式（发现差异时退出码为 1，适用于 CI/CD）
python scripts/reconcile_payments.py --strict

# 5. 限制输出记录数（默认 10）
python scripts/reconcile_payments.py --limit 20

# 6. 组合使用（常用于发布前验收）
python scripts/reconcile_payments.py --date 2025-10-22 --strict --csv
```

**输出示例**（无差异）：

```
=== Reconciliation Summary ===
range: 2025-10-22T00:00:00+00:00 ~ 2025-10-23T00:00:00+00:00
differences: 0

orders_missing_payment: 0
orders_missing_refund: 0
unmatched_payments: 0

✅ reconciliation clean
```

**输出示例**（有差异）：

```
=== Reconciliation Summary ===
range: 2025-10-22T00:00:00+00:00 ~ 2025-10-23T00:00:00+00:00
differences: 3

orders_missing_payment: 2
  - {'order_id': 123, 'order_number': 'NA20251022120345-001234', 'total_price': 45.00}
  - {'order_id': 124, 'order_number': 'NA20251022120456-001235', 'total_price': 38.50}

orders_missing_refund: 0

unmatched_payments: 1
  - {'pay_id': 456, 'channel': 'wechat_native', 'amount': 50.00, 'paid_at': '2025-10-22T14:30:00'}

⚠️ differences detected, manual investigation required
```

**退出码**：

- `0`：对账完成且无差异，或有差异但未启用 `--strict`
- `1`：启用 `--strict` 时发现差异

**适用场景**：

1. **日常运维**：每日凌晨自动运行，检查前一天订单与支付记录一致性
2. **发布前验收**：在部署流水线中添加 `python scripts/reconcile_payments.py --strict`，差异时阻止发布
3. **手动排查**：财务对账时指定日期范围导出 CSV，逐条核对
4. **CI 集成**：在 GitLab CI/GitHub Actions 中定期运行，差异时发送告警通知

**定时任务配置**（cron 示例）：

```bash
# 每日凌晨 1 点对前一天对账，差异时发送告警邮件
0 1 * * * cd /path/to/naicha-backend && /path/to/.venv/bin/python scripts/reconcile_payments.py --strict --csv || echo "Reconciliation failed" | mail -s "对账差异告警" ops@example.com
```

**Kubernetes CronJob 示例**：

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
spec:
  schedule: "0 1 * * *"  # 每日凌晨 1 点
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: reconcile
            image: naicha-backend:latest
            command:
            - python
            - scripts/reconcile_payments.py
            - --strict
            - --csv
          restartPolicy: OnFailure
```

---

### 对账差异排查流程

1. **查看执行日志**
   - 日志关键字：`reconciliation.summary` / `reconciliation.csv_written`
   - 指标：`reconciliation_run_total{result=*}`、`reconciliation_diff_count{type=*}`
   - Redis 锁：`celery:lock:run_daily_reconciliation` 长时间存在 ⇒ 上次任务可能异常退出，可在确认无执行实例后手动 `DEL`

2. **核对差异**
   ```sql
   SELECT order_id, order_number, status, total_price, created_at
   FROM orders
   WHERE order_id = ANY(:order_ids);
   ```
   ```sql
   SELECT pay_id, record_type, amount, match_status, matched_order_id
   FROM payment_records
   WHERE pay_id = ANY(:pay_ids);
   ```
3. **CSV 导出**
   - Flag：`RECONCILIATION_CSV_ENABLED=true`
   - 目录：`RECONCILIATION_REPORT_DIR`（默认空，不导出）
4. **常见场景**
   - POS 未及时建单 → `orders_without_payment`
   - 静态码二维码重复被扫 → `unmatched_payments`
   - 退款手工处理 → `orders_without_refund`
5. **恢复步骤**
   - 人工比对后，补建订单或更新支付记录 `match_status`
   - CSV 失败：确认磁盘权限、剩余空间；必要时关闭 Flag 仅记录日志

---

## 自动降级演练流程

1. **准备**
   - 确认家里节点与云端节点均为 Ready，Prometheus 目标正常
   - 记录当前核心指标：HTTP 成功率、P95 延迟、队列深度
2. **执行步骤**
   1. 断开家庭节点的 WireGuard（或关闭本地 K3s 节点）
   2. 观察 5 分钟：
      - 家节点 `NotReady` ⇒ WAF/Ingress 应只剩云端节点
      - 业务请求保持成功率 ≥99%，P95 波动 <20%
   3. 恢复 WireGuard 连接，确认家节点重新 Ready，但仍为热备
3. **验证**
   - 查看 `kubectl get pods -o wide`，确认流量只指向云端节点
   - 检查 Prometheus：云端 CPU/内存平稳、家节点 0 QPS
4. **记录**
   - 演练用时、发现的问题与改进项，归档至 `doc/degrade-log/`（待落地）
5. **常见问题**
   - WAF 缓存未刷新 ⇒ 手动刷新或降低 TTL
   - 家节点恢复后自动分流 ⇒ 核对 Ingress 权重或 Service Selector

> 演练计划按季度执行，必要时与对账任务一并复盘。
