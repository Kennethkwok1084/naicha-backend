# 运维 Runbook（M4 新增功能）

## 目录
1. [监控指标与告警阈值](#监控指标与告警阈值)
2. [POS 快速建单故障排查](#pos-快速建单故障排查)
3. [静态码支付匹配故障排查](#静态码支付匹配故障排查)
4. [数据看板异常排查](#数据看板异常排查)

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
