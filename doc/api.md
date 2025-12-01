# API 变更记录模板

创建或修改任何 API 时，请复制下列模板并更新对应字段。每个接口一次变更占用一个条目，按时间倒序追加到文档中。

---

## 最新变更

### 微信小程序登录
- **状态**：新增（日期：2025-11-29）
- **路径/方法**：`POST /api/v1/users/login`
- **权限**：公开
- **幂等要求**：是（基于微信code的SHA256哈希防重放）
- **限流**：10次/分钟/IP
- **请求头**：无特殊要求
- **请求体**：
```json
{
  "code": "061abc7d0f2abc3d0f2abc3d0f2abc3d",
  "nickname": "用户昵称",
  "avatar_url": "https://thirdwx.qlogo.cn/..."
}
```
- **字段说明**：
  - `code`: 微信登录一次性code（必填）
  - `nickname`: 用户昵称（可选，长度≤100，自动HTML转义和限长50）
  - `avatar_url`: 用户头像URL（可选，长度≤500，必须http/https）
- **响应体**：
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user_id": 12345,
  "is_new_user": true,
  "token_type": "bearer",
  "expires_in": 7200
}
```
- **字段说明**：
  - `access_token`: 访问令牌，有效期2小时（默认）
  - `refresh_token`: 刷新令牌，有效期30天（默认）
  - `user_id`: 用户ID
  - `is_new_user`: 是否新注册用户
  - `token_type`: 固定值"bearer"
  - `expires_in`: access_token过期时间（秒）
- **错误码**：
  - 400 Bad Request - code已使用或无效
  - 429 Too Many Requests - 超过限流阈值
  - 500 Internal Server Error - 微信API调用失败
- **副作用**：
  1. 调用微信jscode2session获取openid/unionid/session_key
  2. code哈希存入`wechat_used_codes`表防重放
  3. 根据openid查询或创建用户记录
  4. 更新用户昵称/头像/unionid（如提供）
  5. 生成JWT token（包含user_id、openid、jti）
- **token结构**：
  - `sub`: 用户ID
  - `scope`: "user"
  - `openid`: 微信openid
  - `jti`: JWT ID（用于黑名单踢下线）
  - `exp`: 过期时间戳
- **安全要求**：
  - WECHAT_APPID/WECHAT_SECRET仅走环境变量
  - session_key不记录日志、不返回前端
  - code仅使用一次，SHA256哈希后存储
  - IP级别限流10次/分钟

### 绑定微信手机号
- **状态**：新增（日期：2025-11-29）
- **路径/方法**：`POST /api/v1/users/phone/bind`
- **权限**：需要Bearer token认证
- **幂等要求**：是（基于微信code的SHA256哈希防重放）
- **限流**：5次/分钟/IP
- **请求头**：
  - `Authorization`: Bearer {access_token}（必填）
- **请求体**：
```json
{
  "code": "061abc7d0f2abc3d0f2abc3d0f2abc3d",
  "guest_session_id": "guest_abc123"
}
```
- **字段说明**：
  - `code`: 微信手机号一次性code（必填）
  - `guest_session_id`: 游客会话ID（可选，用于追踪转化来源）
- **响应体**：
```json
{
  "phone": "138****5678",
  "from_guest_session": false,
  "message": "手机号绑定成功"
}
```
- **字段说明**：
  - `phone`: 脱敏后的手机号
  - `from_guest_session`: 是否从游客会话转换
  - `message`: 结果消息
- **错误码**：
  - 400 Bad Request - code已使用或无效
  - 401 Unauthorized - 未登录或token无效
  - 429 Too Many Requests - 超过限流阈值
  - 500 Internal Server Error - 微信API调用失败
- **副作用**：
  1. 验证当前用户token有效性
  2. 调用微信API获取手机号（需access_token）
  3. code哈希存入`wechat_used_codes`表防重放
  4. 更新用户手机号字段
- **安全要求**：
  - 必须登录状态
  - 手机号明文仅在日志中脱敏显示
  - code仅使用一次
  - IP级别限流5次/分钟

### 批量上报用户行为埋点
- **状态**：新增 （日期：2025-11-23）
- **路径/方法**：`POST /api/v1/analytics/events`
- **权限**：公开（可选JWT认证，匿名用户需X-Session-Id）
- **幂等要求**：是（基于 `events[].id` UUID主键去重）
- **限流**：100 req/min/IP（应用内 SlowAPI）
- **请求头**：
  - `X-Session-Id`: 会话标识（**匿名用户必填**）
  - `Authorization`: Bearer token（可选）
- **请求体**：
```json
{
  "events": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "event",
      "name": "add_to_cart",
      "timestamp": 1700000000000,
      "payload": {
        "productId": 123,
        "productName": "珍珠奶茶",
        "quantity": 2,
        "price": 15.0
      }
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "type": "page",
      "name": "page_view",
      "timestamp": 1700000001000,
      "payload": {
        "path": "/pages/menu/index",
        "referrer": "/pages/index/index",
        "duration": 3500
      }
    }
  ]
}
```
- **字段说明**：
  - `events[]`: 事件数组，**单次最多10条**
  - `id`: UUID v4 唯一标识（前端生成）
  - `type`: 事件类型 - `event`(操作) / `page`(页面) / `user`(用户属性)
  - `name`: 事件名称（字母、数字、下划线、连字符组合，1-50字符）
  - `timestamp`: Unix毫秒时间戳
  - `payload`: 自定义事件属性（可选）
    - 最多30个字段
    - 总大小≤8KB（序列化后）
    - 嵌套深度≤4层
- **响应体**：`204 No Content`（空响应体）
- **错误码**：
  - 400 Bad Request - 匿名用户缺少 X-Session-Id
  - 400 Bad Request - events 数组为空或超过10条
  - 413 Payload Too Large - 请求体超过32KB
  - 422 Unprocessable Entity - 事件格式校验失败
    - payload 字段数量超过30个
    - payload 总大小超过8KB
    - payload 嵌套层级超过4层
    - 事件名格式非法
    - 批次内存在重复的事件ID
  - 429 Too Many Requests - 超过限流阈值（100次/分钟）
- **副作用**：
  1. 事件整批投递到 Celery 队列（`analytics` 队列）
  2. Worker 异步批量插入数据库（5秒内，`ON CONFLICT DO NOTHING`）
  3. Prometheus 指标上报：
     - `analytics_events_received_total{event_type}`: API接收事件数
     - `analytics_events_inserted_total{event_type}`: 成功入库事件数
     - `analytics_events_duplicates_total`: 重复事件数
- **审计记录**：否（不写入 `audit_logs`，仅存储至 `analytics_events` 表）
- **数据存储**：
  - 表名：`analytics_events`
  - 主键：`event_id UUID` 实现幂等去重
  - 索引：按 `user_id + event_timestamp`, `event_name + event_timestamp`, `session_id + event_timestamp` 优化查询
- **观测指标**：
  - `analytics_events_received_total{event_type}` - API接收事件总数（按类型）
  - `analytics_events_inserted_total{event_type}` - 成功入库事件数（按类型）
  - `analytics_events_duplicates_total` - 重复事件数（主键冲突）
  - `analytics_events_failed_total` - 入库失败次数（重试耗尽）
  - `analytics_batch_insert_duration_seconds` - 批量插入耗时（秒）
  - `analytics_batch_size` - 每批次插入的事件数量
- **测试清单**：
  - [x] 正常流（已登录用户上报）
  - [x] 正常流（匿名用户携带X-Session-Id上报）
  - [x] 参数校验（payload过大、嵌套过深、字段数超限）
  - [x] 参数校验（匿名用户缺少X-Session-Id）
  - [x] 幂等性（重复UUID被自动忽略）
  - [ ] 限流测试（100次/分钟）
  - [ ] 并发测试（多进程同时上报）
  - [ ] 性能测试（API响应≤20ms，入库延迟≤5秒）
- **前端触发时机**：
  - 每隔15秒自动批量上报
  - 累积10条事件时立即上报
  - 页面关闭前上报剩余事件（`beforeunload`）
- **数据可靠性保证**：
  - Celery `task_acks_late=True`: 任务执行完才确认，失败自动重新投递
  - Celery `task_reject_on_worker_lost=True`: Worker异常退出时拒绝任务（重新入队）
  - Celery 自动重试: 最多3次，每次间隔10秒
  - Redis Broker `visibility_timeout=3600`: 1小时可见性超时（避免长事务重复投递）
  - PostgreSQL 主键约束: 最终幂等保证
- **部署要求**：
  - API服务: 可多进程/多副本运行
  - Celery Worker: 独立 `analytics` 队列，建议2-4个worker
    - 启动命令: `celery -A app.workers.celery_app worker -Q analytics,default -l info --concurrency=4`
  - Redis Broker: 确保持久化已开启（AOF或RDB）
- **变更历史**：
  - 2025-11-23：首次发布，支持批量埋点上报

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

### 绑定手机号
- **状态**：新增 （日期：2025-11-24）
- **路径/方法**：`POST /api/v1/users/phone/bind`
- **权限**：用户 JWT | 游客（需 `guest_session_id`）
- **幂等要求**：否
- **限流**：继承全局 SlowAPI 设置
- **请求体**：
```json
{
  "code": "getPhoneNumber-code",
  "guest_session_id": "gs_xxx"
}
```
- **字段说明**：
  - `code`：微信 `getPhoneNumber` 返回码，必填。
  - `guest_session_id`：游客绑定时必填，登录用户可不填。
- **响应体**：
```json
{
  "phone_number": "13800001234",
  "from_guest_session": false
}
```
- **错误码**：
  - 400 code 为空或 guest_session_id 无效/过期。
- **副作用**：
  - 登录用户：写入 `users.preferences_json.phone_number`
  - 游客：回填到 `idempotency_keys.response_snapshot` 供后续下单使用
- **审计记录**：无
- **测试清单**：
  - [x] 登录用户绑定
  - [x] 游客携带 guest_session_id 绑定
  - [ ] 错误码校验（code 为空 / 会话过期）
- **变更历史**：
  - 2025-11-24：首次发布

### 获取门店基础信息
- **状态**：新增 （日期：2025-10-15）；更新 （日期：2025-10-31）
- **路径/方法**：`GET /api/v1/shop/profile`
- **权限**：公开
- **幂等要求**：是（读接口）
- **限流**：继承全局 SlowAPI 设置
- **响应体**：
```json
{
  "name": "奈茶王府井店",
  "address": "北京市东城区王府井大街1号",
  "phone": "010-66668888",
  "announcement": "双十一全场 8 折！",
  "logo_url": "https://cdn.example.com/logo.png",
  "updated_at": "2025-10-15T08:00:00+08:00",
  "delivery_notes": [
    "配送范围：门店周边1.5公里内",
    "配送时间：9:00-21:00",
    "满50元免配送费，不满收取5元配送费",
    "最低起送金额20元"
  ],
  "supports_pickup": true,
  "supports_delivery": true,
  "min_delivery_amount": "20.00",
  "delivery_fee": "5.00",
  "free_delivery_amount": "50.00"
}
```
- **错误码**：
  - 503 Shop profile snapshot 不存在。—— 缓存文件缺失/未初始化
  - 503 Shop profile snapshot 校验失败。—— 缓存内容字段缺失或非法
- **数据来源**：
  - 基础信息（name/address/phone/announcement等）：Redis `SHOP_PROFILE_CACHE_KEY`（默认 `shop:profile`），缺失时回退到本地快照 `app/data/shop_profile.json`
  - 配送配置（delivery_fee等）：从数据库 `shop_settings` 表读取（快照优先）
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补（建议关注前端缓存命中率）
- **测试清单**：
  - [x] 正常流
  - [x] 缺失快照文件
  - [ ] 并发一致性
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-15：首次发布
  - 2025-10-31：新增 delivery_notes、supports_pickup/delivery、配送费用配置字段

### 获取门店营业状态
- **状态**：新增 （日期：2025-10-10）；更新 （日期：2025-10-31）
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
  },
  "business_hours_today": "营业中 09:00-21:00"
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
  - 2025-10-31：新增 business_hours_today 字段（今日营业时间可读文案）

### 广告配置获取
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`GET /api/v1/ads/config`
- **权限**：公开
- **幂等要求**：是
- **限流**：继承 SlowAPI 全局配置
- **请求体**（Query 示例）：
```json
{
  "slots": "HOME_BANNER,HOME_CARD",
  "platform": "miniapp",
  "ver": 1698765432
}
```
- **响应体**：
```json
{
  "version": 1698765440,
  "slots": {
    "HOME_BANNER": [
      {
        "creative_id": 1,
        "title": "秋季新品",
        "image_url": "https://cdn.example.com/banner.png",
        "jump_type": "miniapp_page",
        "jump_payload": {"path": "/pages/menu/index"},
        "tags": ["launch"],
        "priority": 10,
        "sort_order": 0
      }
    ]
  }
}
```
- **错误码**：
  - 422 slots 缺失或为空 —— 请求参数不合法
- **副作用**：读缓存 / 读库
- **审计记录**：否
- **观测指标**：可追加 `ads_config_request_total`
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（缺少 slots）
  - [x] 版本一致返回空集
  - [ ] 并发 / 性能
- **变更历史**：
  - 2025-11-05：首次发布

### 广告曝光打点
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`POST /api/v1/ads/track/expose`
- **权限**：公开
- **幂等要求**：否
- **限流**：继承 SlowAPI 全局配置
- **请求体**：
```json
{
  "slot": "HOME_BANNER",
  "creative_id": 1,
  "user_id": 123,
  "session_id": "gs_xxx"
}
```
- **响应体**：`204 No Content`
- **错误码**：
  - 422 参数缺失 —— 请求体不合法
- **副作用**：写日志
- **审计记录**：否
- **观测指标**：待补 `ads_expose_total`
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验
- **变更历史**：
  - 2025-11-05：首次发布

### 广告点击打点
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`POST /api/v1/ads/track/click`
- **权限**：公开
- **幂等要求**：否
- **限流**：继承 SlowAPI 全局配置
- **请求体**：
```json
{
  "slot": "HOME_BANNER",
  "creative_id": 1,
  "user_id": 123,
  "session_id": "gs_xxx"
}
```
- **响应体**：`204 No Content`
- **错误码**：
  - 422 参数缺失 —— 请求体不合法
- **副作用**：写日志
- **审计记录**：否
- **观测指标**：待补 `ads_click_total`
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验
- **变更历史**：
  - 2025-11-05：首次发布

### 广告位列表
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`GET /api/v1/admin/ads/slots`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：是
- **限流**：`30 req/min/管理员`（应用内）
- **请求体**：无
- **响应体**：
```json
[
  {
    "slot_id": 1,
    "code": "HOME_BANNER",
    "name": "首页轮播",
    "description": "顶部轮播位",
    "spec": {"max_count": 5},
    "created_at": "2025-11-05T08:00:00Z"
  }
]
```
- **错误码**：无
- **副作用**：读库
- **审计记录**：否
- **观测指标**：待补 `admin_ads_slot_list_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
- **变更历史**：
  - 2025-11-05：首次发布

### 创建广告位
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`POST /api/v1/admin/ads/slots`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "code": "HOME_BANNER",
  "name": "首页轮播",
  "description": "顶部轮播位",
  "spec": {"max_count": 5}
}
```
- **响应体**：与“广告位列表”单项结构一致
- **错误码**：
  - 409 广告位编码重复 —— code 已存在
- **副作用**：写库（ad_slots）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_slot_create_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 重复编码
- **变更历史**：
  - 2025-11-05：首次发布

### 更新广告位
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`PUT /api/v1/admin/ads/slots/{slot_code}`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "name": "首页轮播",
  "description": "顶部轮播位",
  "spec": {"max_count": 6}
}
```
- **响应体**：与“广告位列表”单项结构一致
- **错误码**：
  - 404 广告位不存在 —— slot_code 无匹配记录
- **副作用**：写库（ad_slots）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_slot_update_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 广告素材列表
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`GET /api/v1/admin/ads/creatives`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：是
- **限流**：`30 req/min/管理员`
- **请求体**（Query 示例）：
```json
{
  "enabled": true,
  "platform": "miniapp"
}
```
- **响应体**：
```json
[
  {
    "creative_id": 1,
    "title": "秋季上新",
    "image_url": "https://cdn.example.com/banner.png",
    "jump_type": "miniapp_page",
    "jump_payload": {"path": "/pages/menu/index"},
    "start_time": null,
    "end_time": null,
    "enabled": true,
    "priority": 10,
    "platforms": ["miniapp"],
    "tags": ["launch"],
    "created_at": "2025-11-05T08:00:00Z",
    "updated_at": "2025-11-05T08:00:00Z"
  }
]
```
- **错误码**：无
- **副作用**：读库
- **审计记录**：否
- **观测指标**：待补 `admin_ads_creative_list_total`
- **测试清单**：
  - [x] 正常流
  - [x] 参数过滤
- **变更历史**：
  - 2025-11-05：首次发布

### 创建广告素材
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`POST /api/v1/admin/ads/creatives`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "title": "秋季上新",
  "image_url": "https://cdn.example.com/banner.png",
  "jump_type": "miniapp_page",
  "jump_payload": {"path": "/pages/menu/index"},
  "priority": 10,
  "platforms": ["miniapp"],
  "tags": ["launch"]
}
```
- **响应体**：与“广告素材列表”单项结构一致
- **错误码**：
  - 422 参数非法 —— jump_type 不在白名单
- **副作用**：写库（ad_creatives）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_creative_create_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
- **变更历史**：
  - 2025-11-05：首次发布

### 更新广告素材
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`PUT /api/v1/admin/ads/creatives/{creative_id}`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "title": "秋季热饮",
  "enabled": true,
  "tags": ["promo"]
}
```
- **响应体**：与“广告素材列表”单项结构一致
- **错误码**：
  - 404 素材不存在 —— creative_id 无匹配记录
- **副作用**：写库（ad_creatives）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_creative_update_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 删除广告素材
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`DELETE /api/v1/admin/ads/creatives/{creative_id}`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：无
- **响应体**：`204 No Content`
- **错误码**：
  - 404 素材不存在 —— creative_id 无匹配记录
- **副作用**：写库（ad_creatives/ad_placements 级联删除）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_creative_delete_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 广告投放列表
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`GET /api/v1/admin/ads/placements`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：是
- **限流**：`30 req/min/管理员`
- **请求体**（Query 示例）：
```json
{
  "slot_code": "HOME_BANNER"
}
```
- **响应体**：
```json
[
  {
    "placement_id": 1,
    "slot_code": "HOME_BANNER",
    "creative_id": 1,
    "sort_order": 0,
    "created_at": "2025-11-05T08:00:00Z",
    "updated_at": "2025-11-05T08:00:00Z",
    "creative": {"creative_id": 1, "title": "秋季上新", "image_url": "https://cdn.example.com/banner.png", "jump_type": "miniapp_page", "jump_payload": {"path": "/pages/menu/index"}, "start_time": null, "end_time": null, "enabled": true, "priority": 10, "platforms": ["miniapp"], "tags": ["launch"], "created_at": "2025-11-05T08:00:00Z", "updated_at": "2025-11-05T08:00:00Z"}
  }
]
```
- **错误码**：
  - 404 广告位不存在 —— slot_code 无匹配记录
- **副作用**：读库
- **审计记录**：否
- **观测指标**：待补 `admin_ads_placement_list_total`
- **测试清单**：
  - [x] 正常流
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 添加广告投放
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`POST /api/v1/admin/ads/placements`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "slot_code": "HOME_BANNER",
  "creative_id": 1,
  "sort_order": 0
}
```
- **响应体**：与“广告投放列表”单项结构一致
- **错误码**：
  - 404 广告位不存在
  - 404 素材不存在
  - 409 素材已存在于广告位
- **副作用**：写库（ad_placements）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_placement_create_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404/409 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 更新投放排序
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`PUT /api/v1/admin/ads/placements/order`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：
```json
{
  "slot_code": "HOME_BANNER",
  "creative_ids": [2, 1]
}
```
- **响应体**：`204 No Content`
- **错误码**：
  - 404 存在未投放的素材 —— creative_ids 与 slot_code 不匹配
- **副作用**：写库（ad_placements）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_placement_reorder_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

### 删除广告投放
- **状态**：新增 （日期：2025-11-05）
- **路径/方法**：`DELETE /api/v1/admin/ads/placements/{placement_id}`
- **权限**：管理员（角色：admin/manager）
- **幂等要求**：否
- **限流**：`10 req/min/管理员`
- **请求体**：无
- **响应体**：`204 No Content`
- **错误码**：
  - 404 投放不存在 —— placement_id 无匹配记录
- **副作用**：写库（ad_placements）
- **审计记录**：否
- **观测指标**：待补 `admin_ads_placement_delete_total`
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [x] 404 分支
- **变更历史**：
  - 2025-11-05：首次发布

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

### 订单价格试算
- **状态**：新增 （日期：2025-10-31）；更新（日期：2025-11-24，统一请求体字段）
- **路径/方法**：`POST /api/v1/orders/calculate-price`（别名：`POST /api/v1/orders/preview`）
- **权限**：用户 JWT | 游客（未登录状态下无法使用优惠券/积分）
- **幂等要求**：否（纯读操作）
- **限流**：SlowAPI `60 req/min/IP`
- **请求体**：
```json
{
  "shop_id": 1,
  "delivery_type": "pickup",
  "dining_type": "takeout",
  "scheduled_at": "2025-10-21T09:30:00+08:00",
  "address": {
    "address": "深圳市南山区科技园",
    "detail": "XX大厦1层",
    "name": "林小白",
    "phone": "13800001234",
    "lat": 22.543096,
    "lng": 114.057865
  },
  "user_phone": "13800001234",
  "coupon_id": 12345,
  "use_points": true,
  "notes": "少冰",
  "items": [
    {
      "product_id": 101,
      "quantity": 2,
      "selected_specs": [
        { "spec_id": 1001, "option_id": 1001, "option_name": "少糖" },
        { "spec_id": 1002, "option_id": 1004, "option_name": "加珍珠", "price_modifier": 2.0 }
      ]
    }
  ],
  "guest_session_id": "gs_xxx"
}
```
- **请求字段说明**：
  - `shop_id`：必填，门店 ID。
  - `delivery_type`：`pickup` / `delivery`，下单/试算共用字段；兼容 `order_type` 作为别名。
  - `dining_type`：可选，就餐方式（`dine-in` / `takeout`）。
  - `scheduled_at`：可选，ISO8601 且必须带时区，预约仅支持自提。
  - `address`：当 `delivery_type=delivery` 时必填，包含 `address/detail/name/phone/lat/lng`。
  - `user_phone`：试算可选，创建订单必填，用于联系，可配合游客会话使用。
  - `coupon_id`：可选，仅登录用户可用。
  - `use_points`：布尔开关，开启后自动按上限使用积分（兼容旧字段 `points_use`）。
  - `notes`：备注，最长 200。
  - `items[].selected_specs`：规格选择，最少包含 `option_id`；服务端按商品映射落库价差。
  - `guest_session_id`：游客必填，来自 `/api/v1/guests/session`。
- **响应体**：
```json
{
  "subtotal": 36.0,
  "coupon_discount": 5.0,
  "points_discount": 1.0,
  "delivery_fee": 6.0,
  "final_amount": 36.0,
  "breakdown": [
    {
      "product_id": 101,
      "product_name": "珍珠奶茶",
      "quantity": 2,
      "base_price": 15.0,
      "specs": [
        {"option_id": 5, "option_name": "椰果", "price_modifier": 3.0}
      ],
      "unit_price": 18.0,
      "subtotal": 36.0
    }
  ],
  "coupon_info": {
    "coupon_id": 12345,
    "type": "amount_off",
    "discount_amount": 5.0,
    "min_order_amount": 20.0,
    "is_applicable": true,
    "reason": ""
  },
  "points_info": {
    "available": 5000,
    "used": 200,
    "discount": 2.0,
    "exchange_rate": 100
  },
  "eta_minutes": 15,
  "eta_text": "预计 15 分钟后可取餐"
}
```
- **字段说明**：
  - `breakdown`：逐行单品明细，含规格与小计。
  - `coupon_info`：优惠券适配结果，不适用时 `is_applicable=false` 并在 `reason` 中说明原因。
  - `points_info`：积分余额与实际抵扣，登录用户即使未使用积分也会返回可用余额。
  - `eta_minutes` / `eta_text`：预计等待/送达时间，按商品数量与配送方式估算。
- **错误码**：
  - 400 商品不存在 / 下架 / 库存不足。
  - 400 未登录却传入 `coupon_id` / `use_points=true`。
  - 400 配送单未提供地址 / 缺少 `shop_id` 或 `delivery_type`。
- **副作用**：无（不写库、不扣库存、不核销优惠券）
- **审计记录**：不记录
- **观测指标**：待补（可追加 `order_calculate_price_latency_ms`）
- **测试清单**：
  - [x] 基础计算（含规格）
  - [x] 优惠券（可用 / 不可用）
  - [x] 积分限额（30% 上限）
  - [x] 配送费（未满 30 收费、满 30 免配送）
  - [ ] 性能阈值（P95 < 50ms）
- **变更历史**：
  - 2025-11-24：请求体改为共用 schema（shop_id/delivery_type/user_phone/use_points/selected_specs）
  - 2025-10-31：首次发布
### 创建订单
- **状态**：新增 （日期：2025-10-17）；更新（日期：2025-11-24，统一请求体并强制联系方式）
- **路径/方法**：`POST /api/v1/orders`
- **权限**：用户 JWT | 游客（需有效 `guest_session_id`）
- **幂等要求**：是 (`Idempotency-Key` 请求头)
- **限流**：应用内 SlowAPI `30 req/min/IP`
- **请求体**：
```json
{
  "shop_id": 1,
  "delivery_type": "pickup",
  "user_phone": "13800001234",
  "notes": "少冰",
  "guest_session_id": "gs_xxx",
  "scheduled_at": "2025-10-21T09:30:00+08:00",
  "coupon_id": 12345,
  "address": {
    "address": "上海市虹口区 XXX 路",
    "detail": "6号楼 101",
    "name": "林小白",
    "phone": "13800001234",
    "lat": 31.2304,
    "lng": 121.4737
  },
  "items": [
    {
      "product_id": 101,
      "quantity": 2,
      "selected_specs": [
        { "spec_id": 201, "option_id": 3001, "option_name": "去冰" },
        { "spec_id": 202, "option_id": 3002, "option_name": "少糖" }
      ]
    }
  ]
}
```
- **请求字段说明**：
  - `shop_id` / `delivery_type` / `items` / `user_phone`：必填，`delivery_type` 兼容 `order_type` 作为别名。
  - `guest_session_id`：游客下单必填，来源 `/api/v1/guests/session`。
  - `scheduled_at`：可选，自提预约时间，需带时区且受开关/容量限制。
  - `coupon_id`：可选，仅登录用户可用，订单创建时会核销。
  - `notes`：备注，最长 200。
  - `items[].selected_specs`：规格选择，至少提供 `option_id`，其余字段用于透传文案。
- **响应字段补充**：
  - `eta_minutes` / `eta_text`：下单时的预计等待/送达时间。
  - `pickup_code`：取餐码（支付成功后生成，未支付为 `null`，可配置前缀/长度）。
  - 取餐码格式配置：`shop_settings` 表中的 `pickup_code_prefix` / `pickup_code_digits` 优先，其次读取 `.env` 中的 `PICKUP_CODE_PREFIX` / `PICKUP_CODE_DIGITS`，总长度不超过 20。
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
  "eta_minutes": 15,
  "eta_text": "预计 15 分钟后可取餐",
  "pickup_code": null,
  "items": [
    {
      "item_id": 1,
      "product_id": 101,
      "product_name": "珍珠奶茶",
      "quantity": 2,
      "unit_price": 13.0,
      "selected_specs": []
    }
  ]
}
```
- **错误码**：
  - 400 缺少 `Idempotency-Key` / 游客缺少 `guest_session_id`。
  - 400 商品不存在 / 下架 / 库存不足 / 配送缺少 address / user_phone 为空。
  - 400 优惠券不存在、已使用或不属于当前用户。
  - 400 预约未开启 / 超出可预约时间 / 档期已满。
  - 409 幂等冲突（重复 Idempotency-Key 与不同请求体）。
- **副作用**：写库 `orders/order_items/idempotency_keys`，扣减库存，必要时占用预约时间段。
- **审计记录**：无
- **观测指标**：
  - `order_create_total{result}`
  - `inventory_deduction_total{result}`
- **测试清单**：
  - [x] 正常流（用户/游客）
  - [x] 幂等（重复提交同一键）
  - [x] 库存扣减与售罄切换
  - [x] 预约容量/营业时间校验
  - [ ] 性能阈值（P95 < 50ms）
- **变更历史**：
  - 2025-11-30：取餐码改为支付成功后生成，支持自定义前缀/位数
  - 2025-11-24：请求体统一（shop_id/delivery_type/user_phone/selected_specs），备注长度收紧
  - 2025-11-08：新增 ETA 与取餐码字段
  - 2025-10-17：首次发布
### 获取订单详情
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：`GET /api/v1/orders/{order_id}`
- **权限**：用户 JWT | 游客（需提供 `guest_session_id`）
- **幂等要求**：是
- **响应体**：`OrderResponseSchema`（含 `eta_minutes`、`eta_text`、`pickup_code`）
- **错误码**：404 订单不存在；403 无权访问
- **副作用**：无

### 获取我的订单列表
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：`GET /api/v1/me/orders`
- **权限**：用户 JWT
- **查询参数**：
  - `limit`（默认20，1-100）
  - `offset`（默认0，>=0）
  - `status`（可选，字符串，多个状态用逗号分隔）允许值：`pending_payment`, `paid`, `in_production`, `ready_for_pickup`, `completed`, `cancelled`, `refund_pending`, `refunded`
- **响应体**：`OrderResponseSchema` 列表（含 ETA、取餐码）
- **错误码**：
  - 400 Invalid status values —— 传入的状态值不合法
  - 401 未登录
- **副作用**：无
- **示例**：
  - `GET /api/v1/me/orders?status=pending_payment` —— 仅返回待支付订单
  - `GET /api/v1/me/orders?status=paid,in_production` —— 返回已支付和制作中的订单

### 地址簿管理
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：
  - `POST /api/v1/me/addresses` 创建
  - `PUT /api/v1/me/addresses/{id}` 更新
  - `DELETE /api/v1/me/addresses/{id}` 删除
- **权限**：用户 JWT
- **说明**：首次创建自动设为默认；设置 `is_default=true` 会清空其它默认地址；删除默认地址时自动择一补位。
- **错误码**：404 地址不存在（更新/删除）
- **副作用**：写库 `user_addresses`

### 集点进度
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：`GET /api/v1/me/stamps`
- **权限**：用户 JWT
- **响应体** 示例：
```json
{
  "total_completed_orders": 12,
  "stamps_in_cycle": 2,
  "rewards_available": 1,
  "cycle_size": 10
}
```
- **说明**：简化版“集10送1”，基于已支付/制作中的订单数推算。

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

### 取消订单
- **状态**：新增 （日期：2025-11-29）
- **路径/方法**：`POST /api/v1/orders/{order_id}/cancel`
- **权限**：用户 JWT | 游客（需匹配 `guest_session_id`）
- **幂等要求**：是（重复取消已取消订单返回 409）
- **限流**：应用内 SlowAPI `100 req/min`
- **查询参数**：
  - `guest_session_id`（可选，字符串）用于游客身份校验
- **请求体**：无
- **响应体**：`OrderResponseSchema`（含更新后的订单状态）
```json
{
  "order_id": 9001,
  "order_number": "20251129123045-NA1234",
  "status": "cancelled",
  "order_type": "pickup",
  "total_price": 26.0,
  "created_at": "2025-11-29T12:30:45Z",
  "is_scheduled": false,
  "scheduled_at": null,
  "eta_minutes": null,
  "eta_text": "订单已取消",
  "pickup_code": null,
  "items": [...]
}
```
- **错误码**：
  - 403 订单不属于当前用户 / 游客会话不匹配
  - 404 订单不存在
  - 409 订单状态非 `pending_payment` 或已支付，无法取消
- **副作用**：
  - 订单状态更新为 `cancelled`
  - 归还库存（`inventory.available_stock` 增加）
  - 释放预约时段（若有 `reservation_slot_id`）
  - 写入审计日志（`actor_type=user|guest`, `action=order.user_cancel`）
- **审计记录**：记录取消操作及库存归还详情
- **观测指标**：可复用现有订单指标
- **测试清单**：
  - [x] 正常流（用户取消待支付订单）
  - [x] 权限校验（跨用户 403、游客 session 不匹配 403）
  - [x] 状态校验（已支付订单返回 409）
  - [x] 库存归还正确
  - [x] 预约时段释放
  - [x] 幂等性（重复取消返回 409）
- **变更历史**：
  - 2025-11-29：首次发布

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

### 获取公共配置
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：`GET /api/v1/config`
- **权限**：公开
- **幂等要求**：是
- **限流**：建议 WAF 300 req/min/IP
- **请求体**：无
- **响应体**：
```json
{
  "version": "1.0.0",
  "ttl_seconds": 600,
  "contact": {"phone": "13800001234", "business_hours": "09:00-21:00"},
  "legal": {"privacy_url": "https://guajunyan.top/privacy.html"},
  "features": {
    "disable_delivery": false,
    "disable_coupons": false,
    "disable_stamps": false
  },
  "ui": {"eta_fallback_text": "前方排队制作中，预计等待时间请留意通知"},
  "assets": {"cdn_base_url": null}
}
```
- **错误码**：
  - 503 公共配置文件不存在。—— 部署缺少 `app/data/app_config.json`
  - 503 公共配置文件格式错误。—— JSON 解析失败或根节点非对象
- **副作用**：读取/写入 Redis 缓存（命中 5 分钟）
- **审计记录**：否
- **观测指标**：待补（建议追加 `public_config_fetch_total`）
- **测试清单**：
  - [x] 合并数据库 features 覆盖静态值
  - [ ] 缓存命中/失效
  - [ ] TTL 透传
- **变更历史**：
  - 2025-11-08：首次发布

### 更新功能开关
- **状态**：新增 （日期：2025-11-08）
- **路径/方法**：`PUT /api/v1/admin/config/features/{feature_key}`
- **权限**：管理员（角色 admin/manager）
- **幂等要求**：是（同一 key 多次写入覆盖）
- **限流**：建议 60 req/min/账号
- **请求体**：
```json
{
  "enabled": true,
  "reason": "台风天气临时关闭配送"
}
```
- **响应体**：
```json
{
  "config_key": "features.disable_delivery",
  "value": true,
  "updated_at": "2025-11-08T10:30:00Z",
  "updated_by_admin_id": 1
}
```
- **错误码**：
  - 400 不支持的功能开关键。—— `feature_key` 不在 {disable_delivery, disable_coupons, disable_stamps}
  - 403 当前账号无权更新配置。—— 非 admin/manager
- **副作用**：写库 `shop_config`；删除 Redis 缓存 key
- **审计记录**：暂不写入
- **观测指标**：待补（建议 `feature_toggle_total`）
- **测试清单**：
  - [x] 写库并清除缓存
  - [ ] 角色拦截
  - [ ] 参数校验（reason 长度）
- **变更历史**：
  - 2025-11-08：首次发布
