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

### 获取积分交易记录
- **状态**：新增 （日期：2025-10-27）
- **路径/方法**：`GET /api/v1/me/loyalty/transactions`
- **权限**：用户 JWT
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **查询参数**：
  - `limit` (可选，默认10，范围1-100): 每页返回的记录数
  - `offset` (可选，默认0): 分页偏移量
- **响应体**：
```json
{
  "transactions": [
    {
      "id": 12345,
      "user_id": 1,
      "order_id": 9001,
      "delta_points": 10,
      "reason": "order_paid",
      "created_at": "2025-10-27T10:30:00Z"
    },
    {
      "id": 12344,
      "user_id": 1,
      "order_id": null,
      "delta_points": -10,
      "reason": "coupon_use",
      "created_at": "2025-10-27T09:15:00Z"
    }
  ],
  "total_count": 25,
  "limit": 10,
  "offset": 0
}
```
- **字段说明**：
  - `reason` 枚举值：
    - `order_paid`: 订单支付完成获得积分
    - `refund_rollback`: 退款回滚扣除积分
    - `coupon_grant`: 积分兑换优惠券扣除积分
    - `coupon_use`: 使用优惠券
  - `delta_points`: 正数为增加积分，负数为减少积分
  - 记录按 `created_at` 降序排列（最新的在前）
- **错误码**：
  - 401 未携带 Token / Token 过期 / Token 非法
  - 422 `limit` 或 `offset` 参数不合法
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流（含空列表、分页）
  - [x] 权限校验
  - [x] 参数校验（limit 范围）
  - [x] 数据隔离（只返回当前用户记录）
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-27：首次发布

### 获取优惠券列表
- **状态**：新增 （日期：2025-10-27）
- **路径/方法**：`GET /api/v1/me/coupons`
- **权限**：用户 JWT
- **幂等要求**：是
- **限流**：继承全局 SlowAPI 设置
- **查询参数**：
  - `status` (可选): 按状态筛选，枚举值：`active`、`used`、`expired`、`void`。不提供时返回所有状态。
- **响应体**：
```json
{
  "coupons": [
    {
      "coupon_id": 10001,
      "user_id": 1,
      "type": "free_any_drink",
      "status": "active",
      "meta_json": {"description": "积分兑换"},
      "issued_at": "2025-10-27T08:00:00Z",
      "used_at": null,
      "used_in_order_id": null,
      "created_at": "2025-10-27T08:00:00Z"
    },
    {
      "coupon_id": 10000,
      "user_id": 1,
      "type": "free_any_drink",
      "status": "used",
      "meta_json": null,
      "issued_at": "2025-10-26T12:00:00Z",
      "used_at": "2025-10-26T15:30:00Z",
      "used_in_order_id": 9001,
      "created_at": "2025-10-26T12:00:00Z"
    }
  ],
  "stats": {
    "total_count": 5,
    "active_count": 2,
    "used_count": 2,
    "expired_count": 1
  }
}
```
- **字段说明**：
  - `type` 枚举值：
    - `free_any_drink`: 任意饮品免单券（免除订单中最便宜的一杯）
  - `status` 枚举值：
    - `active`: 可用
    - `used`: 已使用
    - `expired`: 已过期
    - `void`: 已作废
  - `stats`: 当前用户优惠券的统计数据
- **错误码**：
  - 401 未携带 Token / Token 过期 / Token 非法
  - 422 `status` 参数值不合法
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流（含空列表、筛选）
  - [x] 权限校验
  - [x] 参数校验（status 枚举值）
  - [x] 数据隔离（只返回当前用户优惠券）
  - [x] 统计数据准确性
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-27：首次发布

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
  "scheduled_at": "2025-10-21T09:30:00+08:00",
  "coupon_id": 12345,
  "address": {
    "contact_name": "林小白",
    "phone": "13800001234",
    "address_line": "上海市虹口区 XXX 路",
    "lat": 31.2304,
    "lng": 121.4737
  }
}
```
- **请求字段说明**：
  - `coupon_id` (可选): 优惠券ID，仅登录用户可用。使用 `free_any_drink` 类型优惠券时，自动免除订单中最便宜的一杯价格。
- **响应体**：
```json
{
  "order_id": 9001,
  "order_number": "20251017153045-NA1234",
  "status": "pending_payment",
  "order_type": "pickup",
  "total_price": 26.0,
  "created_at": "2025-10-17T15:30:45.123456+00:00",
  "is_scheduled": true,
  "scheduled_at": "2025-10-21T01:30:00+00:00",
  "reminder_sent_at": null,
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
  - 400 缺少 `Idempotency-Key` / 游客缺少 `guest_session_id` / 商品或规格已下架 / 预约档期已满 / 优惠券不存在、已使用或不属于当前用户
  - 422 预约时间不合法（非当日/未在营业时间/未带时区）
  - 403 游客会话不匹配目标订单
  - 409 Idempotency-Key 与历史请求不一致
- **预约容量**：默认以 `RESERVATION_SLOT_GRANULARITY_MINUTES=15` 分钟为档期粒度，且每个档期至多 `RESERVATION_SLOT_CAPACITY=10` 单（可通过环境变量调优）
- **副作用**：写库 `orders`、`order_items`、`idempotency_keys`
- **审计记录**：暂不写入
- **观测指标**：
  - `order_create_total{result=success|service_error|unexpected_error}`
  - `inventory_deduction_total{result=success|insufficient|restored}`
  - `inventory_current_stock{product_id}`
  - `inventory_oversell_total{product_id}`
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（游客无 session、规格越权）
  - [ ] 权限校验
  - [x] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-17：首次发布
  - 2025-10-24：支持预约下单（`scheduled_at` 字段，需携带时区；仅 pickup，当日+提前 15 分钟）

### 提交「想要」事件
- **状态**：新增 （日期：2025-10-24）
- **路径/方法**：`POST /api/v1/products/{product_id}/want`
- **权限**：登录用户 JWT（优先使用用户 ID） | 游客（根据客户端 IP 哈希）
- **幂等要求**：否（服务侧 1 分钟限频）
- **限流**：SlowAPI `20/minute`（key：用户 ID 或 IP）
- **请求体**：无
- **响应体**：
```json
{
  "product_id": 101,
  "created_at": "2025-10-24T03:10:00Z",
  "source": "user"
}
```
- **错误码**：
  - 404 Product not available —— 商品已下架或不存在
  - 429 Want rate limit exceeded —— 同一用户/IP 1 分钟仅允许一次
  - 503 Want feature is disabled —— Feature Flag `want_enabled` 关闭
- **副作用**：写入 `want_events`（记录 user_id/ip_hash/user_agent），触发 `/menu` 缓存刷新
- **审计记录**：否
- **观测指标**：后续补充（计划 `want_event_total`）
- **测试清单**：
  - [x] 登录用户/游客流
  - [x] 限流（用户 ID 与 IP 分别判定）
  - [x] Feature Flag 关闭
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-24：首次发布

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
- **路径/方法**：`POST /api/v1/payments/notify/wechat`（兼容：`POST /payments/notify/wechat`）
- **权限**：微信渠道（签名头 `X-Wechat-Signature`）
- **幂等要求**：是（以 `transaction_id` 去重）
- **限流**：应用内 SlowAPI `300 req/s` + `18000 req/min/IP`
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
- **副作用**：写库 `payment_records`、`orders.status=paid`、补写 `print_jobs`、触发商户 WS 推送、累计会员积分（满 10 杯自动发放 `free_any_drink` 券）
- **审计记录**：暂不写入
- **观测指标**：
  - `payment_callback_total{result=success|order_not_found|conflict|unexpected_error}`
  - `payment_callback_latency_ms`
  - `payment_callback_duplicate_total{channel}`
  - `print_job_total{result=success|missing|retry_scheduled|non_retryable_failure|retry_limit}`
  - `print_job_retry_count`
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
{"type": "print_job.failed", "job": {"job_id": 321,"order_id": 9001,"try_count": 5}, "order": {"order_id": 9001,"order_number": "20251017153045-NA1234","status": "paid"}, "error": "打印服务返回错误: 400"}
```
- **错误码**：
  - WS Close `1008` Missing token —— 未携带 Token
  - WS Close `1008` Insufficient scope —— 非管理员 Token
- **副作用**：实时推送订单状态（依赖内存广播，后续可扩展 Redis Stream）
- **审计记录**：暂不记录
- **观测指标**：
  - `ws_connections_active`
  - `ws_broadcast_fail_total`
  - `print_job_total{result=print_job.failed 推送对应 result}` (用于监控失败通知量)
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
  - `print_job_total{result=success|retry_scheduled|non_retryable_failure}`
  - `print_job_recovery_total{result=recovered|empty}`
- **测试清单**：
  - [x] 正常流（cash/wechat）
  - [x] 幂等复用
  - [x] 角色与渠道限制
  - [x] 打印任务与广播
  - [x] 看板缓存刷新
- **变更历史**：
  - 2025-10-21：首次发布（M4）

### 待支付订单手动自动取消
- **状态**：新增 （日期：2025-10-28）
- **路径/方法**：`POST /api/v1/ops/orders/auto-cancel`
- **权限**：管理员 JWT（角色：admin/manager；用于应急触发）
- **幂等要求**：否（每次调用都会重新扫描）
- **限流**：建议通过网关限制 6 req/min/IP
- **请求体**：
```json
{
  "cutoff_minutes": 45,
  "limit": 100,
  "reason": "auto_cancel.ops_drill"
}
```
- **字段说明**：
  - `cutoff_minutes`：扫描创建时间早于当前 `cutoff_minutes` 的待支付订单（默认 30，范围 1-1440）
  - `limit`：本次最多取消订单数（默认 100，上限 500）
  - `reason`：自定义审计原因，默认 `auto_cancel.manual_trigger`
- **响应体**：
```json
{
  "cancelled_order_ids": [5001, 5002],
  "count": 2,
  "cutoff_iso": "2025-10-28T03:10:00Z",
  "source": "http",
  "operator_admin_id": 101
}
```
- **错误码**：
  - 403 当前账号无权执行自动取消任务 —— 非 admin/manager
  - 422 cutoff_minutes/limit 超出允许范围
- **副作用**：逐条调用 `OrderService.cancel_pending_order()`，回补库存、写 `audit_logs`（action=`order.auto_cancel`），累加指标 `orders_auto_cancelled_total{source="http"}`、`orders_auto_cancel_delay_seconds`
- **审计记录**：继承 `order.auto_cancel` + 记录 `reason` 与 `operator_admin_id`
- **观测指标**：
  - `orders_auto_cancelled_total{source=celery|http|cron,result=success|not_found|not_pending}`
  - `orders_auto_cancel_delay_seconds{source=...}`
- **测试清单**：
  - [x] 触发成功（回补库存 + 状态变更）
  - [x] 权限拦截（clerk 禁止）
  - [ ] 大批量基准测试
- **变更历史**：
  - 2025-10-28：首次发布（M6）

### 更新商品库存状态
- **状态**：新增 （日期：2025-10-24）
- **路径/方法**：`PUT /api/v1/admin/inventory/products/{product_id}`
- **权限**：管理员 JWT（角色：admin/manager）
- **幂等要求**：是（重复写同状态无副作用）
- **限流**：SlowAPI `20/minute`（key：管理员 Token/IP）
- **请求体**：
```json
{
  "inventory_status": "sold_out"
}
```
- **响应体**：
```json
{
  "product_id": 101,
  "inventory_status": "sold_out",
  "updated_at": "2025-10-24T03:12:00Z"
}
```
- **错误码**：
  - 403 Insufficient role for inventory updates —— 非 admin/manager 角色
  - 404 Product not found —— 商品不存在
  - 422 inventory_status must be in_stock or sold_out
- **副作用**：写库 `products.inventory_status`，写入 `audit_logs`（action=`admin.inventory.product.update`），触发菜单缓存失效
- **审计记录**：记录 admin_id、前后状态、IP、UA
- **观测指标**：待补（计划 `inventory_update_total{type="product"}`）
- **测试清单**：
  - [x] 商品售罄与恢复
  - [x] 权限拦截
  - [x] 菜单缓存刷新
- **变更历史**：
  - 2025-10-24：首次发布

### 更新规格库存状态
- **状态**：新增 （日期：2025-10-24）
- **路径/方法**：`PUT /api/v1/admin/inventory/spec-options/{option_id}`
- **权限**：管理员 JWT（角色：admin/manager）
- **幂等要求**：是
- **限流**：SlowAPI `20/minute`
- **请求体**：同上
- **响应体**：
```json
{
  "spec_option_id": 3001,
  "inventory_status": "sold_out",
  "updated_at": "2025-10-24T03:12:15Z"
}
```
- **错误码**：
  - 403 Insufficient role for inventory updates
  - 404 Spec option not found
  - 422 inventory_status must be in_stock or sold_out
- **副作用**：写库 `spec_options.inventory_status`，写审计（action=`admin.inventory.spec_option.update`），刷新 `/menu` 缓存
- **审计记录**：记录 admin_id、前后状态、IP、UA
- **观测指标**：同上（type=`spec_option`）
- **测试清单**：
  - [x] 规格售罄与恢复
  - [x] 权限拦截
  - [x] 菜单缓存刷新
- **变更历史**：
  - 2025-10-24：首次发布

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

### 想要统计概览
- **状态**：新增 （日期：2025-10-24）
- **路径/方法**：`GET /api/v1/admin/want/stats`
- **权限**：管理员 JWT
- **幂等要求**：是（读接口；限流 10 req/min/admin）
- **查询参数**：
  - `range=1d|7d|30d`（默认 7d）
  - `limit`（默认 20，范围 1~100）
- **响应体**：
```json
{
  "range": "7d",
  "start": "2025-10-17T16:00:00Z",
  "end": "2025-10-24T15:59:59Z",
  "top_products": [
    {"product_id": 101, "product_name": "阿萨姆奶茶", "total": 56}
  ],
  "daily_series": [
    {"date": "2025-10-18", "count": 8},
    {"date": "2025-10-19", "count": 5}
  ]
}
```
- **错误码**：
  - 422 Unsupported range —— `range` 不在白名单
- **副作用**：无
- **审计记录**：否
- **观测指标**：待补（计划 `want_stats_query_latency_ms`）
- **测试清单**：
  - [x] 默认 7 日窗口
  - [x] range 白名单校验
  - [x] TopN 补零
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-24：首次发布

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
