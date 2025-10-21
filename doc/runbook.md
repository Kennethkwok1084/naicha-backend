# 运维 Runbook（M4-M5 新增功能）

## 目录
1. [监控指标与告警阈值](#监控指标与告警阈值)
2. [POS 快速建单故障排查](#pos-快速建单故障排查)
3. [静态码支付匹配故障排查](#静态码支付匹配故障排查)
4. [数据看板异常排查](#数据看板异常排查)
5. [预约提醒任务排查](#预约提醒任务排查)
6. [售罄/库存刷新排查](#售罄库存刷新排查)
7. [「想要」统计排查](#想要统计排查)
8. [每日对账任务排查](#每日对账任务排查)
9. [自动降级演练流程](#自动降级演练流程)

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
3. **检查任务堆积**
   ```sql
   SELECT *
   FROM celery_taskmeta
   WHERE task_name LIKE 'app.workers.tasks.reservation_%'
   ORDER BY date_done DESC
   LIMIT 20;
   ```
4. **常见问题**
   - 调整营业时间：更新 `shop_profile.open_hours_json` 后立即生效
   - 提醒未发送：确认 `reservation_reminder_minutes` 是否 >=5；过小会被验证拒绝
5. **恢复步骤**
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
   - 若多实例部署，缓存 TTL=240s，最长 5 分钟同步；Runbook 中注明此延迟为预期
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

1. **查看执行日志**
   - 日志关键字：`reconciliation.summary` / `reconciliation.csv_written`
   - 指标：`reconciliation_run_total{result=*}`、`reconciliation_diff_count{type=*}`
2. **核对差异**
   ```sql
   SELECT order_id, order_number, payment_status, status, total_price
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
