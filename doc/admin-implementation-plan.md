# 管理后台完整实施计划

> 基于当前代码审查和需求文档分析  
> 日期：2025-12-01  
> 状态：规划中

---

## 当前已完成模块

### ✅ Step 1: 认证与权限基础（已完成）
- [x] `app/core/permissions.py` - 40+权限点定义与角色映射
- [x] `app/api/routes/admin/auth.py` - 登录、获取当前用户信息
- [x] `app/utils/audit.py` - 审计日志工具与装饰器
- [x] 路由模块化拆分（8个子模块）

### ✅ Step 2: 订单管理（已完成）
- [x] 订单列表（分页+10种过滤条件）
- [x] 订单详情（含用户信息、时间线）
- [x] 订单状态修改（含审计）
- [x] 订单退款（online/offline模式，含审计）
- [x] 取餐码修改（唯一性校验，含审计）

### ⚠️ 现有模块（功能不完整）
- **POS下单** (`pos.py`) - 基础功能存在
- **支付匹配** (`payments.py`) - 静态码匹配，**缺审计日志**
- **Dashboard** (`dashboard.py`) - 仅支持range/compare，**缺自定义日期区间、Top商品**
- **库存管理** (`inventory.py`) - 产品/规格库存状态更新，**缺审计日志**
- **Want统计** (`want.py`) - 基础统计，功能完整
- **广告管理** (`ads.py`) - 广告位/素材/投放管理，**缺审计日志**

---

## 缺失模块清单

### 🔴 高优先级（核心业务）

#### P0 - 商品/分类/规格管理（CRUD）
**数据模型：** 已存在（`app/models/catalog.py`）
- `Category` - 分类
- `Product` - 商品
- `SpecGroup` - 规格组
- `SpecOption` - 规格选项
- `ProductSpecMapping` - 商品规格映射
- `ProductCategory` - 商品分类映射

**缺失功能：**
- [ ] 分类CRUD（创建、编辑、删除、排序）
- [ ] 商品CRUD（创建、编辑、上下架、删除）
- [ ] 规格组/选项CRUD
- [ ] 商品规格映射管理
- [ ] 批量导入商品（Excel/CSV）
- [ ] 商品图片上传
- [ ] 审计日志集成

**权限点（已定义）：**
- `products.view`, `products.edit`, `products.delete`, `products.import`
- `categories.view`, `categories.edit`, `categories.delete`
- `specs.view`, `specs.edit`, `specs.delete`

#### P0 - 会员管理
**数据模型：** 部分存在（`app/models/accounts.py`）
- `User` - 用户表（已有）
- `LoyaltyTransaction` - 积分流水（已有）
- ❌ **缺失：储值账户模型**（需新建 `WalletAccount`, `WalletTransaction`）

**缺失功能：**
- [ ] 会员列表（搜索、过滤、分页）
- [ ] 会员详情（基础信息、订单历史、积分/储值明细）
- [ ] 手动调整积分（含原因、审计）
- [ ] 储值充值/扣减（含原因、审计）
- [ ] 会员标签/分组管理
- [ ] 会员导出

**权限点（已定义）：**
- `members.view`, `members.edit`, `members.asset.adjust`

#### P1 - 营销管理（优惠券）
**数据模型：** 部分存在
- `Coupon` - 优惠券表（已有，但字段可能不足）
- ❌ **缺失：优惠券模板、发券记录、使用统计**

**缺失功能：**
- [ ] 优惠券模板CRUD（满减、折扣、固定金额）
- [ ] 批量发券（按用户筛选、标签、手机号）
- [ ] 优惠券使用统计
- [ ] 优惠券核销记录查询
- [ ] 审计日志集成

**数据库建模：**
```sql
-- 需新建表
CREATE TABLE coupon_templates (
    template_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL, -- discount/amount/percentage
    discount_value NUMERIC(10,2),
    min_order_amount NUMERIC(10,2),
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    total_quantity INT,
    per_user_limit INT,
    status VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE coupon_issues (
    issue_id BIGSERIAL PRIMARY KEY,
    template_id BIGINT REFERENCES coupon_templates,
    user_id BIGINT REFERENCES users,
    code VARCHAR(50) UNIQUE,
    status VARCHAR(20), -- issued/used/expired
    used_at TIMESTAMP,
    order_id BIGINT,
    created_at TIMESTAMP
);
```

**权限点（已定义）：**
- `marketing.coupons.view`, `marketing.coupons.edit`, `marketing.coupons.issue`

### 🟡 中优先级（运营支撑）

#### P1 - 门店配置管理
**数据模型：** 已存在（`app/models/shop.py`）
- `ShopProfile` - 门店档案
- `ShopConfig` - 门店配置
- `ShopSetting` - 门店设置

**缺失功能：**
- [ ] 门店基础信息CRUD
- [ ] 营业时间配置
- [ ] 营业状态控制（营业中/打烊/休息）
- [ ] 配送范围设置
- [ ] 门店公告管理
- [ ] 审计日志集成

**权限点（已定义）：**
- `shop.settings.view`, `shop.settings.edit`

#### P1 - 管理员管理
**数据模型：** 已存在（`app/models/accounts.py`）
- `Admin` - 管理员表

**缺失功能：**
- [ ] 管理员列表
- [ ] 管理员创建/编辑（角色分配）
- [ ] 管理员禁用/启用
- [ ] 重置密码
- [ ] 登录日志查询
- [ ] 审计日志集成

**权限点（已定义）：**
- `system.admins.view`, `system.admins.manage`

#### P2 - 审计日志查询/导出
**数据模型：** 已存在（`app/models/orders.py`）
- `AuditLog` - 审计日志表

**缺失功能：**
- [ ] 审计日志列表（分页、过滤：操作人、操作类型、时间范围、风险等级）
- [ ] 审计日志详情（before/after对比）
- [ ] 日志导出（CSV/Excel）
- [ ] 操作统计（按管理员、按操作类型）

**权限点（已定义）：**
- `system.audit.view`, `system.audit.export`

#### P2 - Webhook管理
**数据模型：** ❌ **完全缺失**

**需要建模：**
```sql
CREATE TABLE webhooks (
    webhook_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    url VARCHAR(500) NOT NULL,
    event_types TEXT[], -- ['order.paid', 'order.completed']
    secret VARCHAR(100), -- 用于签名验证
    status VARCHAR(20), -- active/disabled
    retry_count INT DEFAULT 3,
    timeout_seconds INT DEFAULT 10,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    created_by_admin_id BIGINT
);

CREATE TABLE webhook_logs (
    log_id BIGSERIAL PRIMARY KEY,
    webhook_id BIGINT REFERENCES webhooks,
    event_type VARCHAR(50),
    payload JSONB,
    response_status INT,
    response_body TEXT,
    retry_count INT,
    created_at TIMESTAMP
);
```

**缺失功能：**
- [ ] Webhook CRUD
- [ ] 测试触发
- [ ] 执行日志查询
- [ ] 失败重试管理
- [ ] 审计日志集成

**权限点（已定义）：**
- `webhooks.view`, `webhooks.manage`

#### P2 - 设备管理（商家端/POS）
**数据模型：** ❌ **完全缺失**

**需要建模：**
```sql
CREATE TABLE devices (
    device_id BIGSERIAL PRIMARY KEY,
    device_type VARCHAR(20), -- pos/printer/display
    device_name VARCHAR(100),
    device_code VARCHAR(50) UNIQUE,
    status VARCHAR(20), -- online/offline/disabled
    last_heartbeat TIMESTAMP,
    ip_address VARCHAR(50),
    mac_address VARCHAR(50),
    shop_id BIGINT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**缺失功能：**
- [ ] 设备注册/绑定
- [ ] 设备列表（在线状态监控）
- [ ] 设备配置管理
- [ ] 设备心跳监控
- [ ] 设备解绑/删除
- [ ] 审计日志集成

**权限点（已定义）：**
- `devices.merchant.view`, `devices.merchant.manage`
- `devices.pos.view`, `devices.pos.manage`

### 🟢 低优先级（增强功能）

#### P3 - Dashboard增强
**当前状态：** `app/api/routes/admin/dashboard.py` 基础功能已完成 ✅

**已实现：**
- [x] 支持自定义日期区间（start_date/end_date，UTC-aware）✅
- [x] Top销售商品（按销量、金额，可配置top_n）✅
- [x] 缓存优化（缓存键包含所有参数）✅
- [x] 时区安全（自定义日期转换为UTC-aware datetime）✅

**待补充：**
- [ ] 新增会员趋势
- [ ] 订单时段分布
- [ ] 支付渠道分布

#### P3 - 统计报表
- [ ] 销售日报/周报/月报
- [ ] 商品销售排行
- [ ] 会员消费分析
- [ ] 优惠券使用分析
- [ ] 报表导出

---

## 审计日志覆盖计划

### 当前审计覆盖情况（已完成现有所有Admin模块）
✅ **已集成模块：**
- `app/api/routes/admin/orders.py` - 订单状态修改、退款、取餐码修改
- `app/services/inventory.py` - 库存调整（服务层审计）✅
- `app/api/routes/admin/payments.py` - 支付匹配 ✅
- `app/api/routes/admin/ads.py` - 广告管理（8个操作）✅
- `app/api/routes/admin/pos.py` - POS下单（_post_create回调中）✅

❌ **尚未开发的模块（无需审计）：**
- 商品/分类/规格管理
- 会员管理
- 营销/优惠券
- 管理员CRUD

### 需要集成审计的操作类型

#### 高风险操作（risk_level=critical）
- 订单退款 ✅
- 订单取消 ✅
- 会员积分调整 ❌（模块未开发）
- 会员储值调整 ❌（模块未开发）
- 优惠券批量发放 ❌（模块未开发）
- 管理员密码重置 ❌（模块未开发）

#### 中风险操作（risk_level=high）
- 订单状态修改 ✅
- 取餐码修改 ✅
- 支付匹配 ✅
- 库存调整 ✅
- 商品上下架 ❌（模块未开发）
- 管理员禁用/启用 ❌（模块未开发）
- Webhook配置修改 ❌（模块未开发）

#### 普通操作（risk_level=normal）
- 广告位配置 ✅（8个操作完整覆盖）
- POS下单 ✅
- 商品创建/编辑 ❌（模块未开发）
- 分类管理 ❌（模块未开发）
- 门店信息修改 ❌（模块未开发）

---

## 退款流程完善计划

### 当前问题
`app/api/routes/admin/orders.py` 的 `refund_order()` 只标记状态，未真正对接支付渠道。

### 需要实现

#### 1. 微信支付退款对接
```python
# app/services/payment/wechat_refund.py
async def process_wechat_refund(
    order_number: str,
    transaction_id: str,
    refund_amount: Decimal,
    reason: str
) -> RefundResult:
    """调用微信支付退款API"""
    # 1. 构建退款请求
    # 2. 调用微信退款接口
    # 3. 处理退款结果
    # 4. 异步查询退款状态
    pass
```

#### 2. 支付宝退款对接
```python
# app/services/payment/alipay_refund.py
async def process_alipay_refund(...) -> RefundResult:
    pass
```

#### 3. 退款状态异步查询
```python
# app/workers/refund_status_checker.py
# 定期查询退款结果，更新订单状态
```

#### 4. 退款Webhook处理
```python
# app/api/routes/webhooks/payment.py
@router.post("/wechat/refund")
async def handle_wechat_refund_callback(...):
    """接收微信退款回调"""
    pass
```

---

## 测试计划

### 当前测试覆盖情况
❌ **无任何Admin路由测试**

### 需要补充的测试

#### 1. 认证与权限测试
```
tests/api/admin/test_auth.py
- test_admin_login_success
- test_admin_login_invalid_credentials
- test_get_current_admin_info
- test_permissions_by_role
```

#### 2. 订单管理测试
```
tests/api/admin/test_orders.py
- test_list_orders_with_filters
- test_list_orders_pagination
- test_get_order_detail
- test_update_order_status_success
- test_update_order_status_permission_denied
- test_cancel_order_without_reason_fails
- test_refund_order_online
- test_refund_order_offline
- test_refund_amount_exceeds_total_fails
- test_update_pickup_code_duplicate_fails
- test_audit_logs_created
```

#### 3. 权限测试（通用）
```
tests/api/admin/test_permissions.py
- test_admin_role_has_all_permissions
- test_manager_role_limited_permissions
- test_clerk_role_readonly
- test_unauthorized_access_returns_403
```

#### 4. 审计日志测试
```
tests/api/admin/test_audit.py
- test_audit_log_recorded_on_critical_operation
- test_audit_log_contains_before_after
- test_require_reason_decorator
```

---

## 文档同步计划

### 1. OpenAPI规范更新
**文件：** `naicha-openapi.json`

**当前问题：** 只包含少量Admin路径

**需要：**
- [ ] 导出完整的OpenAPI规范（`/openapi.json`）
- [ ] 同步所有Admin路由定义
- [ ] 补充请求/响应Schema
- [ ] 补充权限要求说明

### 2. API文档更新
**文件：** `doc/api.md`

**已完成：** 订单管理5个接口 ✅

**需补充：**
- [ ] 商品/分类/规格管理接口
- [ ] 会员管理接口
- [ ] 营销管理接口
- [ ] 门店配置接口
- [ ] 管理员管理接口
- [ ] 审计日志接口
- [ ] Webhook管理接口
- [ ] 设备管理接口
- [ ] Dashboard增强接口

---

## 实施时间表（建议）

### Sprint 1（1-2周）- 核心CRUD补全
- [ ] 商品/分类/规格管理（完整CRUD + 审计）
- [ ] 现有模块审计日志集成（inventory, payments, ads）
- [ ] Dashboard增强（自定义日期、Top商品）
- [ ] 测试覆盖（认证、权限、订单）

### Sprint 2（1-2周）- 会员与营销
- [ ] 储值账户建模与迁移
- [ ] 会员管理完整功能
- [ ] 优惠券模板与发券功能
- [ ] 测试覆盖（会员、营销）

### Sprint 3（1周）- 门店与管理员
- [ ] 门店配置管理
- [ ] 管理员CRUD与权限管理
- [ ] 审计日志查询/导出
- [ ] 测试覆盖

### Sprint 4（1-2周）- Webhook与设备
- [ ] Webhook建模与CRUD
- [ ] 设备管理建模与CRUD
- [ ] 退款流程对接支付渠道
- [ ] 测试覆盖

### Sprint 5（1周）- 文档与优化
- [ ] 完整API文档更新
- [ ] OpenAPI规范导出
- [ ] 性能优化与缓存
- [ ] 集成测试与压测

---

## 下一步行动

**建议优先级：**
1. **补充现有模块审计日志**（快速提升安全性）
2. **Dashboard增强**（改善管理体验）
3. **商品管理CRUD**（核心业务功能）
4. **测试补充**（保证质量）
5. **会员与营销模块**（业务扩展）

**立即可开始的工作：**
- 给 `inventory.py`、`payments.py`、`ads.py` 添加审计日志
- Dashboard支持自定义日期区间和Top商品
- 补充 `tests/api/admin/` 测试用例

**需要讨论的决策点：**
- 储值账户的业务规则（充值方式、使用优先级、退款规则）
- 优惠券系统的复杂度（是否支持叠加、排他、组合规则）
- Webhook的安全机制（签名算法、重试策略）
- 设备管理的绑定流程（是否需要审批）
