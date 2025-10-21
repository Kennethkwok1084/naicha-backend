# API 变更记录模板

创建或修改任何 API 时，请复制下列模板并更新对应字段。每个接口一次变更占用一个条目，按时间倒序追加到文档中。

```markdown
### [API 名称]
- **状态**：新增 | 修改 | 弃用 | 删除  （日期：YYYY-MM-DD）
- **路径/方法**：`[METHOD] /api/v1/...`
- **权限**：公开 | 用户 JWT | 管理员 | 服务内部
- **幂等要求**：是 (`Idempotency-Key`) | 否
- **限流**：示例 `60 req/min/用户`（注明执行位置：WAF / 应用内 SlowAPI）
- **请求体**（示例 + 字段说明）：
```json
{
  "field": "value"
}
```
- **响应体**（示例 + 字段说明）：
```json
{
  "code": 0,
  "data": { ... },
  "trace_id": "..."
}
```
- **错误码**：列出业务错误（含 HTTP 状态、触发场景）
- **副作用**：写库 / 调度任务 / 打印 / 推送 / 观测打点 等
- **审计记录**：是否写入 `audit_logs`，需要保留的关键信息
- **观测指标**：涉及的 Prometheus 指标名（示例：`order_create_total`、`payment_callback_latency_ms`）
- **测试清单**：
  - [ ] 正常流
  - [ ] 参数校验
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - YYYY-MM-DD：说明
```

> **提示**：接口实现提交时必须同步更新本文件以及 OpenAPI 文档，缺失会阻塞合并。

---

### 管理员登录
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`POST /api/v1/admin/login`
- **权限**：公开（需提供合法用户名/密码）
- **幂等要求**：否
- **限流**：待与 WAF 统一配置（建议 30 req/min/账号）
- **请求体**：
```json
{
  "username": "admin",
  "password": "secret123"
}
```
- **响应体**：
```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```
- **错误码**：
  - 401 Invalid username or password. —— 认证失败
- **副作用**：无
- **审计记录**：暂不写入（仅登录成功返回 JWT）
- **观测指标**：待补（计划补充登录成功/失败计数）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（错误凭据）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 用户登录（Code → OpenID）
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`POST /api/v1/users/login`
- **权限**：公开（凭小程序 code）
- **幂等要求**：否
- **限流**：待配置（建议 60 req/min/device）
- **请求体**：
```json
{
  "code": "mock-openid",
  "nickname": "小明",
  "avatar_url": "https://example.com/avatar.png"
}
```
- **响应体**：
```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user": {
    "user_id": 1,
    "nickname": "小明",
    "avatar_url": "https://example.com/avatar.png",
    "loyalty_points": 0
  }
}
```
- **错误码**：
  - 400 Invalid authorization code. —— code 为空或非法
- **副作用**：写库 `users`（创建/更新昵称、头像）
- **审计记录**：暂不记录
- **观测指标**：待补（计划 code 兑换成功/失败计数）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（空 code）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 获取门店营业状态
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`GET /api/v1/shop/status`
- **权限**：公开
- **幂等要求**：是（读接口）
- **限流**：继承全局 SlowAPI 设置
- **响应体**：
```json
{
  "is_open": true,
  "delivery_radius_m": 1500,
  "timezone": "Asia/Shanghai",
  "open_hours": [
    {
      "weekday": 1,
      "ranges": [["09:00", "21:00"]]
    }
  ],
  "location": {
    "lat": 31.2304,
    "lng": 121.4737
  },
  "features": {
    "multi_category_enabled": true,
    "reservation_enabled": false,
    "want_enabled": true
  }
}
```
- **错误码**：无
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补（可追加 P95 latency、缓存命中率）
- **测试清单**：
  - [x] 正常流
  - [ ] 参数校验
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 检查配送范围
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`POST /api/v1/shop/delivery/check`
- **权限**：公开
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **请求体**：
```json
{
  "lat": 31.2304,
  "lng": 121.4737
}
```
- **响应体**：
```json
{
  "deliverable": true,
  "distance_m": 123.45
}
```
- **错误码**：
  - 503 Shop location not configured. —— 门店未配置经纬度
  - 422 Validation Error —— 经纬度超出范围
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补（建议输出 `delivery_check_total`）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（缺失位置/越界）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 获取菜单（含缓存）
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`GET /api/v1/menu`
- **权限**：公开
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **响应体**：
```json
{
  "multi_category_enabled": true,
  "categories": [
    {
      "category_id": 1,
      "name": "热销",
      "sort_order": 1,
      "products": [
        {
          "product_id": 1,
          "name": "珍珠奶茶",
          "description": "经典款",
          "image_url": null,
          "base_price": 12.5,
          "status": "active",
          "inventory_status": "in_stock",
          "spec_groups": [
            {
              "group_id": 1,
              "name": "糖度",
              "sort_order": 1,
              "options": [
                {
                  "option_id": 1,
                  "name": "正常糖",
                  "price_modifier": 0.0,
                  "inventory_status": "in_stock",
                  "sort_order": 1
                }
              ]
            }
          ]
        }
      ]
    }
  ],
  "uncategorized_products": []
}
```
- **错误码**：无
- **副作用**：无（只读，命中缓存 TTL 240 秒；调用 `invalidate_menu_cache()` 主动失效）
- **审计记录**：不记录
- **观测指标**：2025-10-11 内存压测 100 次 —— `/menu` P95 ≈1.6ms、平均 1.4ms，缓存命中率 0.99
- **测试清单**：
  - [x] 正常流
  - [x] 缓存校验（命中、手动失效、库存状态变更自动刷新）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [x] 性能阈值（本地压测 100 次）
- **变更历史**：
  - 2025-10-10：首次发布

### 游客会话创建/续期
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`POST /api/v1/guests/session`
- **权限**：公开
- **幂等要求**：否（允许重复请求返回同一 session）
- **限流**：继承全局 SlowAPI 设置（建议 60 req/min/device）
- **请求体**：
```json
{
  "session_token": "gs_existing"
}
```
- **响应体**：
```json
{
  "guest_session_id": "gs_xxx",
  "expires_at": "2025-11-10T12:00:00Z"
}
```
- **错误码**：无
- **副作用**：写库 `idempotency_keys(scope='guest_session')`
- **审计记录**：不记录
- **观测指标**：待补（建议记录创建量、续期量）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（空 body）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 获取当前用户资料
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`GET /api/v1/me/profile`
- **权限**：用户 JWT
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **响应体**：
```json
{
  "user_id": 1,
  "nickname": "小明",
  "avatar_url": "https://example.com/avatar.png",
  "loyalty_points": 12
}
```
- **错误码**：
  - 401 Authorization header missing. —— 未携带 Token
  - 401 Token expired —— Token 过期
  - 401 Token invalid —— Token 被篡改/非法
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 异常流（过期/篡改 Token）
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 获取用户地址簿
- **状态**：新增 （日期：2025-10-10）
- **路径/方法**：`GET /api/v1/me/addresses`
- **权限**：用户 JWT
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **响应体**：
```json
[
  {
    "address_id": 1,
    "contact_name": "张三",
    "phone": "13800000000",
    "address_line": "上海市徐汇区",
    "lat": 31.23,
    "lng": 121.47,
    "is_default": true,
    "created_at": "2025-10-10T08:00:00Z",
    "updated_at": "2025-10-10T08:00:00Z"
  }
]
```
- **错误码**：
  - 401 Authorization header missing. —— 未携带 Token
  - 401 Token expired —— Token 过期
  - 401 Token invalid —— Token 被篡改/非法
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流（含空列表）
  - [x] 权限校验
  - [x] 异常流（过期/篡改 Token）
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布

### 创建订单
- **状态**：新增 （日期：2025-10-17）
- **路径/方法**：`POST /api/v1/orders`
- **权限**：用户 JWT | 游客（需有效 `guest_session_id`）
- **幂等要求**：是 (`Idempotency-Key` 请求头)
- **限流**：应用内 SlowAPI `30 req/min/IP`
- **请求体**：
```json
{
  "items": [
    {
      "product_id": 101,
      "quantity": 2,
      "spec_option_ids": [1001, 1002]
    }
  ],
  "order_type": "pickup",
  "notes": "少冰",
  "guest_session_id": "gs_xxx",
  "address": {
    "contact_name": "林小白",
    "phone": "13800001234",
    "address_line": "上海市虹口区 XXX 路",
    "lat": 31.2304,
    "lng": 121.4737
  }
}
```
- **响应体**：
```json
{
  "order_id": 9001,
  "order_number": "20251017153045-NA1234",
  "status": "pending_payment",
  "order_type": "pickup",
  "total_price": 26.0,
  "created_at": "2025-10-17T15:30:45.123456+00:00",
  "items": [
    {
      "item_id": 12345,
      "product_id": 101,
      "product_name": "桂花乌龙",
      "quantity": 2,
      "unit_price": 13.0,
      "selected_specs": [
        {
          "group_id": 100,
          "group_name": "甜度",
          "option_id": 1001,
          "option_name": "半糖",
          "price_modifier": 0.0
        }
      ]
    }
  ]
}
```
- **错误码**：
  - 400 缺少 `Idempotency-Key` / 游客缺少 `guest_session_id` / 商品或规格已下架
  - 403 游客会话不匹配目标订单
  - 409 Idempotency-Key 与历史请求不一致
- **副作用**：写库 `orders`、`order_items`、`idempotency_keys`
- **审计记录**：暂不写入
- **观测指标**：待补（计划 `order_create_total`, `order_create_fail_total`）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（游客无 session、规格越权）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布

### 发起微信 JSAPI 支付
- **状态**：新增 （日期：2025-10-17）
- **路径/方法**：`POST /api/v1/orders/{order_id}/pay/jsapi`
- **权限**：用户 JWT | 游客（需匹配 `guest_session_id`）
- **幂等要求**：否
- **限流**：应用内 SlowAPI `60 req/min/IP`
- **请求体**：
```json
{
  "payer_open_id": "wx1234567890",
  "guest_session_id": "gs_xxx"
}
```
- **响应体**：
```json
{
  "order_id": 9001,
  "channel": "wechat_jsapi",
  "payload": {
    "prepay_id": "mock_prepay_20251017153045-NA1234",
    "nonce_str": "5f8c2e4a6b7c8d90",
    "timestamp": "1697541045",
    "sign": "6f5c...e9",
    "payer_open_id": "wx1234567890"
  }
}
```
- **错误码**：
  - 403 订单不属于当前用户 / 游客会话不匹配
  - 404 订单不存在
  - 409 订单状态非 `pending_payment`
- **副作用**：无
- **审计记录**：暂不写入
- **观测指标**：待补（计划 `payment_initiate_total`）
- **测试清单**：
  - [x] 正常流
  - [ ] 参数校验
  - [x] 权限校验（跨用户 403）
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布

### 发起微信 Native 支付
- **状态**：新增 （日期：2025-10-17）
- **路径/方法**：`POST /api/v1/orders/{order_id}/pay/native`
- **权限**：用户 JWT | 游客（需匹配 `guest_session_id`）
- **幂等要求**：否
- **限流**：应用内 SlowAPI `60 req/min/IP`
- **请求体**：
```json
{
  "guest_session_id": "gs_xxx"
}
```
- **响应体**：
```json
{
  "order_id": 9001,
  "channel": "wechat_native",
  "payload": {
    "code_url": "https://pay.mock/wechat/native/20251017153045-NA1234"
  }
}
```
- **错误码**：
  - 403 订单不属于当前用户 / 游客会话不匹配
  - 404 订单不存在
  - 409 订单状态非 `pending_payment`
- **副作用**：无
- **审计记录**：暂不写入
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流
  - [ ] 参数校验
  - [x] 权限校验（跨用户 403）
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布

### 微信支付回调
- **状态**：新增 （日期：2025-10-17）
- **路径/方法**：`POST /api/v1/payments/notify/wechat`
- **权限**：微信渠道（签名头 `X-Wechat-Signature`）
- **幂等要求**：是（以 `transaction_id` 去重）
- **限流**：应用内 SlowAPI `120 req/min/IP`
- **请求体**：
```json
{
  "event_id": "evt_123",
  "order_number": "202510170001-NA0001",
  "transaction_id": "wx-transaction",
  "amount": 17.0,
  "currency": "CNY",
  "channel": "wechat_jsapi",
  "status": "SUCCESS",
  "paid_at": "2025-10-17T07:16:24.123456+00:00"
}
```
- **响应体**：
```json
{
  "status": "SUCCESS"
}
```
- **错误码**：
  - 401 Invalid signature. —— 回调签名校验失败
  - 404 Order not found for payment notification. —— 订单不存在或已删除
  - 409 Payment amount mismatches order total. —— 支付金额与订单不一致
- **副作用**：写库 `payment_records`、`orders.status=paid`、补写 `print_jobs`、触发商户 WS 推送、累计会员积分（满 10 自动发放 `free_any_drink` 券）
- **审计记录**：暂不写入
- **观测指标**：待补（计划 `payment_callback_total`、`payment_callback_fail_total`、`payment_callback_latency_ms`）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（签名、金额不一致）
  - [x] 幂等 / 重放
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布

### 商户订单推送 WebSocket
- **状态**：新增 （日期：2025-10-17）
- **路径/方法**：`WS /ws/merchant?token=<admin_jwt>`
- **权限**：管理员 JWT（Query 参数 `token`）
- **幂等要求**：是（重复连接会踢出旧连接）
- **限流**：WAF/Ingress 层控制（建议 60 conn/min/IP）
- **消息示例**：
```json
{"type": "connection.ready", "admin_id": 1}
{"type": "order.paid.snapshot", "orders": [{"order_id": 500,"order_number": "202510170500-NA0001","status": "paid","paid_at": "2025-10-17T07:20:00+00:00"}]}
{"type": "order.paid", "order": {"order_id": 9001,"order_number": "20251017153045-NA1234","total_price": 26.0,"status": "paid","paid_at": "2025-10-17T07:31:45+00:00"}}
```
- **错误码**：
  - WS Close `1008` Missing token —— 未携带 Token
  - WS Close `1008` Insufficient scope —— 非管理员 Token
- **副作用**：实时推送订单状态（依赖内存广播，后续可扩展 Redis Stream）
- **审计记录**：暂不记录
- **观测指标**：待补（计划 `ws_connections_active`、`ws_broadcast_fail_total`）
- **测试清单**：
  - [x] 正常流（离线补推 + 心跳）
  - [x] 权限校验（缺失 Token）
  - [ ] 多实例广播 / 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布

### POS 快速建单
- **状态**：新增 （日期：2025-10-21）
- **路径/方法**：`POST /api/v1/admin/orders`
- **权限**：管理员 JWT（角色：admin/manager/clerk；clerk 仅可使用 cash/pos_card）
- **幂等要求**：是（`X-Idempotency-Key` 必填，每管理员 10 req/min）
- **请求体**：
```json
{
  "items": [{"product_id": 101, "spec_option_ids": [201], "quantity": 2}],
  "payment_channel": "cash",
  "notes": "少冰",
  "print_job": true,
  "buyer_open_id": "wx-openid-123"
}
```
- **响应体**：
```json
{
  "order_id": 123,
  "order_number": "20251021163001-NA1234",
  "status": "paid",
  "payment_status": "paid",
  "payment_channel": "cash",
  "total_price": 36.0,
  "created_at": "2025-10-21T08:30:01Z",
  "print_job_id": 456
}
```
- **错误码**：
  - 400 Invalid JSON body / X-Idempotency-Key header missing
  - 403 Insufficient role for POS order creation / Clerk role can only use in-store payment channels
  - 409 order.out_of_stock / product.inactive / order.concurrent_conflict
  - 422 buyer_open_id or guest_session_id is required
  - 503 print.service_unavailable（打印服务不可用，仅记录日志）
- **副作用**：写库 `orders`、`order_items`，写 `audit_logs`（action=`pos.order.create`），触发 WebSocket `order.created`，打印任务入队，刷新看板缓存
- **审计记录**：记录 admin_id、IP、User-Agent、订单要素
- **观测指标**：
  - `admin_order_created_total{channel=...,result=success|error}`
  - `admin_order_create_latency_ms{channel=...}`
- **测试清单**：
  - [x] 正常流（cash/wechat）
  - [x] 幂等复用
  - [x] 角色与渠道限制
  - [x] 打印任务与广播
  - [x] 看板缓存刷新
- **变更历史**：
  - 2025-10-21：首次发布（M4）

### 静态码支付匹配
- **状态**：新增 （日期：2025-10-21）
- **路径/方法**：`POST /api/v1/admin/payments/match`
- **权限**：管理员 JWT
- **幂等要求**：否（匹配流程内部保证状态）
- **请求体**：
```json
{
  "qr_session_id": "qr-20251021-001",
  "amount": 28.0,
  "paid_at": "2025-10-21T08:05:00Z",
  "transaction_id": "txn-static-001",
  "trace_id": "trace-abc",
  "force_order_id": null
}
```
- **响应体（唯一匹配）**：
```json
{
  "status": "matched",
  "payment_record_id": 9001,
  "order_id": 321,
  "order_number": "202510211605-NA0001",
  "payment_channel": "static_qr",
  "payment_status": "paid"
}
```
- **错误码**：
  - 404 payment.match_not_found —— 未找到候选
  - 409 payment.match_ambiguous —— 多个候选（响应包含 candidates）
  - 409 payment.match_conflict —— 金额不符 / 订单已支付
  - 422 paid_at / amount / force_order_id 校验失败
- **副作用**：写 `payment_records` 匹配状态，更新 `orders` 支付状态，创建打印任务、刷新看板缓存，写 `audit_logs`（action=`admin.payment.match`），触发 WebSocket `order.paid`，积分与发券幂等发放
- **审计记录**：记录 admin_id、匹配到的 payment_record_id / order_id、trace_id、IP、UA
- **观测指标**：
  - `payment_match_attempt_total{result=matched|ambiguous|not_found|conflict}`
  - `loyalty_points_awarded_total{reason='order_paid'}`
  - `coupon_issued_total{reason='loyalty10'}`
- **测试清单**：
  - [x] 唯一匹配
  - [x] 冲突（金额不符 / 已支付）
  - [x] 多候选（返回 candidates）
  - [x] 人工 force 匹配
  - [x] 幂等积分/发券
- **变更历史**：
  - 2025-10-21：首次发布（M4）

### 商家数据看板
- **状态**：新增 （日期：2025-10-21）
- **路径/方法**：`GET /api/v1/admin/dashboard`
- **权限**：管理员 JWT
- **幂等要求**：是（读接口；缓存 60s；限流 30 req/min/admin）
- **查询参数**：
  - `range=day|week|month`（默认 day）
  - `compare=true|false`（默认 false）
- **响应体**：
```json
{
  "range": "day",
  "summary": {"gross_sales": 1250.0, "order_count": 85, "avg_ticket": 14.7, "refund_amount": 60.0},
  "trend": [{"ts": "2025-10-21T02:00:00Z", "gross_sales": 210.0, "order_count": 14}],
  "top_products": [{"product_id": 101, "name": "红茶拿铁", "quantity": 35, "gross_sales": 525.0}],
  "payment_channel_split": [{"channel": "wechat_jsapi", "order_count": 45, "gross_sales": 630.0}],
  "compare_summary": {"gross_sales": 980.0, "order_count": 70, "avg_ticket": 14.0, "refund_amount": 40.0}
}
```
- **错误码**：
  - 422 Unsupported dashboard range
- **副作用**：无写操作；POS / 静态码匹配成功时刷新缓存
- **审计记录**：否
- **观测指标**：
  - `admin_dashboard_query_latency_ms{range=...}`
- **测试清单**：
  - [x] 日维度统计 + 对比
  - [x] 趋势 / Top5 / 渠道拆分计算
  - [x] 非法参数校验
- **变更历史**：
  - 2025-10-21：首次发布（M4）
