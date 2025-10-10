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
- **观测指标**：待补（计划缓存命中率、构建耗时）
- **测试清单**：
  - [x] 正常流
  - [x] 参数校验（缓存失效逻辑）
  - [ ] 权限校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
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
  - 401 Token invalid —— Token 失效
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流
  - [x] 权限校验
  - [ ] 参数校验
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
- **副作用**：无
- **审计记录**：不记录
- **观测指标**：待补
- **测试清单**：
  - [x] 正常流（含空列表）
  - [x] 权限校验
  - [ ] 参数校验
  - [ ] 幂等 / 并发
  - [ ] 性能阈值
- **变更历史**：
  - 2025-10-10：首次发布
