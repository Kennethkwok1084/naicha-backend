# 奶茶管理平台 Web 管理端开发设计文档（develop.md）

> 版本：v1.0  
> 状态：完成版（随业务演进更新）  
> 范围：**仅针对 Web 管理端（Admin Web）及其依赖的管理侧 API 需求**  
> 后端实现细节以 Naicha Backend 统一代码基座为准

---

## 1. 文档目的与阅读对象

本开发文档用于指导 **奶茶管理平台 Web 管理端** 的设计与开发，实现从 PRD 到代码的落地。重点包括：

- Web 管理端前端架构设计、路由/状态管理规范；
- 管理端所依赖的 `/api/v1/admin/**` 接口定义与补充需求；
- 模块级页面设计（订单、商品、会员、营销、广告位、门店、设备、Webhook、审计等）；
- 鉴权、安全与审计相关约定（从 Web 视角）。

阅读对象：

- 前端开发（Admin Web）
- 后端开发（Admin API 相关）
- 产品/测试（理解功能边界与接口约定）

---

## 2. 范围与整体架构

### 2.1 范围说明

本 develop.md 仅覆盖：

- Web 管理端（浏览器访问的后台管理界面）；
- 管理端所需的 Admin API 设计与补充（`/api/v1/admin/**`）。

**不在本文件范围内：**

- 小程序/H5 C 端前台；
- POS 客户端 UI 细节；
- Naicha Backend 内部领域实现与数据库具体 SQL；
- k3s 部署、CI/CD 等运维细节（由 ops 文档单独描述）。

### 2.2 管理端整体架构视图

- 前端：
  - 技术栈：React + TypeScript + Vite
  - UI 组件库：Ant Design
  - 状态管理：React Query（数据拉取与缓存）+ 少量 Zustand/Redux（全局 UI/用户信息）；
  - 路由：React Router
  - 构建：Vite + pnpm/yarn

- 后端（对 Web 管理端暴露）：
  - 统一前缀：`/api/v1/admin/**`
  - 服务部署：`naicha-admin-api` 服务实例（与 `naicha-public-api` 分离部署）；
  - 鉴权：JWT 或短期 Access Token + 可选 Refresh Token + 2FA；
  - 审计：所有写操作由 Admin API 写入审计日志表 `admin_operation_logs`。

前端 Admin Web 只通过 HTTP(S) 与 `naicha-admin-api` 交互，不直接与数据库、消息队列或 POS 通道通信。与 POS/商家端之间的联动通过后端事件完成。

---

## 3. 前端设计

### 3.1 技术栈与基础约束

- 语言：TypeScript（严格开启 `strict`）
- 框架：React 18+
- 构建工具：Vite
- UI：Ant Design
- 网络：fetch 封装 / axios 二选一，推荐 axios（内置拦截器）
- 数据请求管理：React Query
- 代码风格：ESLint + Prettier + Husky（可选）

### 3.2 目录结构建议

```text
admin-web/
  src/
    api/              # API 封装（按业务模块拆分）
      auth.ts
      orders.ts
      products.ts
      members.ts
      marketing.ts
      ads.ts
      shops.ts
      devices.ts
      webhooks.ts
      audit.ts
    pages/            # 页面级组件
      Login/
      Dashboard/
      Orders/
      Products/
      Members/
      Marketing/
      Ads/
      Shop/
      Devices/
      Webhooks/
      System/
    components/       # 共享组件
      Layout/
      Table/
      Form/
      Charts/
      Audit/
    router/
      index.tsx       # 路由定义
      guards.tsx      # 权限守卫
    store/
      authStore.ts    # 登录态、角色、权限点
      uiStore.ts      # 全局 UI 状态
    utils/
      request.ts      # axios 封装
      auth.ts         # token 处理、2FA 等
      formatters.ts
      constants.ts
    types/            # TS 公共类型定义
      api.ts
      domain.ts
    main.tsx
    App.tsx
```

### 3.3 路由设计

所有业务路由需经过登录与权限守卫。

```ts
// 示例路由结构（伪代码）
const routes = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <MainLayout />, // 顶层布局，含侧边栏/顶部导航
    children: [
      { path: '/dashboard', element: <DashboardPage />, meta: { perm: 'dashboard.view' } },
      { path: '/orders', element: <OrderListPage />, meta: { perm: 'orders.view' } },
      { path: '/orders/:id', element: <OrderDetailPage />, meta: { perm: 'orders.view' } },
      { path: '/products', element: <ProductListPage />, meta: { perm: 'products.view' } },
      { path: '/products/new', element: <ProductEditPage />, meta: { perm: 'products.edit' } },
      { path: '/products/:id/edit', element: <ProductEditPage />, meta: { perm: 'products.edit' } },
      { path: '/members', element: <MemberListPage />, meta: { perm: 'members.view' } },
      { path: '/members/:id', element: <MemberDetailPage />, meta: { perm: 'members.view' } },
      { path: '/marketing/coupons', element: <CouponTemplateListPage />, meta: { perm: 'marketing.coupons.view' } },
      { path: '/ads', element: <AdsSlotPage />, meta: { perm: 'ads.view' } },
      { path: '/shop/settings', element: <ShopSettingsPage />, meta: { perm: 'shop.settings.edit' } },
      { path: '/devices/merchant', element: <MerchantDevicesPage />, meta: { perm: 'devices.merchant.view' } },
      { path: '/devices/pos', element: <PosDevicesPage />, meta: { perm: 'devices.pos.view' } },
      { path: '/webhooks', element: <WebhooksPage />, meta: { perm: 'webhooks.manage' } },
      { path: '/system/admins', element: <AdminAccountsPage />, meta: { perm: 'system.admins.manage' } },
      { path: '/system/audit', element: <AuditLogPage />, meta: { perm: 'system.audit.view' } },
    ],
  },
];
```

路由守卫逻辑：

- 未登录跳转 `/login`；
- 已登录但角色为 Guest，自动屏蔽所有写操作按钮；
- 若缺少路由对应权限点，则返回 403 页面或隐藏菜单入口。

### 3.4 状态与权限管理

- 登录成功后，前端持有：
  - `accessToken`
  - 当前管理员信息：`id`, `username`, `role`, `permissions: string[]`

- 权限控制策略：
  - 菜单、路由、按钮按 `permissions` 进行前端控制；
  - 实际安全控制以后端为准：后端在每个写操作接口检查权限点。

### 3.5 UI 规范

- 表格统一使用 `Antd Table`，支持：分页、搜索区域、列宽可调；
- 表单统一使用 `Antd Form`，支持：校验、重置；
- 重要写操作前必须弹出确认弹窗（如退款、资产调整、设备解绑等）；
- 对于需要备注的操作（如积分调整、退款、取餐码修改），前端强制要求填写原因字段。  

---

## 4. 鉴权与安全设计（Web 视角）

### 4.1 登录与 Token 流程

1. 登录表单提交：
   - `POST /api/v1/admin/login`
   - 请求：`{ username, password, otpCode? }`
   - 返回：`{ accessToken, refreshToken?, admin: { id, username, role, permissions } }`

2. 前端行为：
   - 将 `accessToken` 存储于内存 + `localStorage`/`sessionStorage`（根据安全策略）；
   - 将基础信息写入 `authStore`；
   - 配置 axios 拦截器，在每个请求中注入 `Authorization: Bearer <accessToken>`；
   - 401 时尝试用 refreshToken 换新（如有），否则跳转登录。

### 4.2 2FA/短信验证

- 后续方案：
  - 登录时若后端返回 `need_2fa = true`，前端引导输入 OTP 或短信验证码；
  - 2FA 验证通过后再签发 token。

2FA 具体 API 可在后续迭代中补充，本版本仅预留前端逻辑结构。

### 4.3 CSRF 与 XSS

- 所有请求通过 Bearer Token 鉴权，不依赖浏览器 cookie 会话；
- 所有输出到页面的文本需进行转义或使用 React 的默认安全渲染；
- 禁止在未充分过滤的情况下使用 `dangerouslySetInnerHTML`。

---

## 5. Admin API 设计与补充

> 说明：以下仅列出 **管理端新增/重点依赖的接口**，已有的 OpenAPI 中存在的接口只做引用，不重复展开实现细节。

统一前缀：`/api/v1/admin`

### 5.1 认证与基础

#### 5.1.1 管理员登录

- `POST /api/v1/admin/login`
- 请求：

```json
{
  "username": "string",
  "password": "string",
  "otp_code": "string (可选)"
}
```

- 响应：

```json
{
  "access_token": "string",
  "refresh_token": "string (可选)",
  "admin": {
    "id": "string",
    "username": "string",
    "role": "SuperAdmin" | "Admin" | "Guest",
    "permissions": ["orders.view", "orders.edit", "members.view", "..."]
  }
}
```

> 说明：实际密码校验 & 2FA 由后端负责。前端需根据 `role` 和 `permissions` 控制 UI。

#### 5.1.2 获取当前管理员信息

- `GET /api/v1/admin/me`
- 返回当前登录管理员基本信息与权限点，供前端初始化。

---

### 5.2 仪表盘

#### 5.2.1 数据看板

- `GET /api/v1/admin/dashboard`
- 查询参数：`range`（`day|week|month|custom`）、`start_date`、`end_date`（可选）
- 返回：
  - 核心指标：订单数、GMV、客单价、退款金额等；
  - 趋势数据：日/小时维度数组；
  - Top 商品列表等。

前端使用折线图/柱状图进行可视化展示。

---

### 5.3 订单模块

#### 5.3.1 订单列表

- `GET /api/v1/admin/orders`
- 查询参数示例：
  - `page`, `page_size`
  - `status`（多选：pending/paid/in_production/ready/completed/cancelled/refunded...）
  - `order_type`（pickup/delivery/dine_in）
  - `start_time`, `end_time`
  - `pay_method`
  - `store_id`
  - `user_phone`
  - `pickup_code`

- 响应：分页列表，包含订单号、取餐码、金额、状态、用户手机号、门店等简要信息。

#### 5.3.2 订单详情

- `GET /api/v1/admin/orders/{order_id}`
- 返回：
  - 订单基础信息
  - 商品明细（含规格、加料）
  - 优惠与活动信息
  - 支付信息
  - 用户信息（手机号明文）
  - 状态流转时间线

#### 5.3.3 修改订单状态

- `PUT /api/v1/admin/orders/{order_id}/status`
- 请求：

```json
{
  "status": "in_production | ready_for_pickup | completed | cancelled",
  "reason": "string (取消或异常状态必填)"
}
```

- 后端需写审计日志，记录状态变更、reason、操作人。

#### 5.3.4 订单退款

- `POST /api/v1/admin/orders/{order_id}/refund`
- 请求：

```json
{
  "refund_type": "online | offline",
  "amount": 32.5,
  "reason": "string (必填)"
}
```

- 在线退款由后端调用支付渠道；线下退款仅标记状态与记账；
- 所有退款操作必须写入审计日志，并标记为高风险操作。

#### 5.3.5 自定义/重置取餐码

- `PUT /api/v1/admin/orders/{order_id}/pickup-code`
- 请求：

```json
{
  "new_pickup_code": "string (可选，若为空则按规则重新生成)",
  "reason": "string (必填)"
}
```

- 响应：包含更新后的取餐码；
- 后端：
  - 校验取餐码唯一性与规则；
  - 写审计日志：记录原取餐码、新取餐码、reason；
  - 产生事件供 POS/小程序更新展示。

---

### 5.4 商品与菜单模块

#### 5.4.1 分类管理

- `GET /api/v1/admin/categories`
- `POST /api/v1/admin/categories`
- `PUT /api/v1/admin/categories/{id}`
- `DELETE /api/v1/admin/categories/{id}`（软删）

字段包含：`name`, `display_order`, `is_visible` 等。

#### 5.4.2 商品管理

- `GET /api/v1/admin/products`
  - 支持按分类、关键字过滤
- `GET /api/v1/admin/products/{id}`
- `POST /api/v1/admin/products`
- `PUT /api/v1/admin/products/{id}`
- `DELETE /api/v1/admin/products/{id}`（软删）

商品结构需支持：

```ts
interface AdminProduct {
  id: string;
  name: string;
  short_name?: string;
  description?: string;
  category_id: string;
  price: number;
  original_price?: number;
  tags?: string[]; // 新品/招牌等
  is_active: boolean; // 上下架
  display_order: number;
  available_time_ranges?: TimeRange[]; // 可售时间段
}
```

#### 5.4.3 Excel 批量导入商品

- `POST /api/v1/admin/products/batch-import`
  - 请求：multipart/form-data 上传 Excel 文件
- 后端处理：
  - 解析 Excel 并校验：
    - 分类是否存在（可选：自动创建）；
    - 字段合法性（价格、必填项）；
  - 返回：

```json
{
  "total": 100,
  "success": 95,
  "failed": 5,
  "errors": [
    { "row": 3, "message": "分类不存在: 奶茶3" },
    { "row": 10, "message": "价格格式错误" }
  ]
}
```

- 日志与审计：批量导入属于高影响操作，应记录操作人、导入总条数、成功/失败条数。

#### 5.4.4 规格组与规格项

- `GET /api/v1/admin/spec-groups`
- `POST /api/v1/admin/spec-groups`
- `PUT /api/v1/admin/spec-groups/{id}`
- `DELETE /api/v1/admin/spec-groups/{id}`

- `GET /api/v1/admin/spec-options?group_id=xxx`
- `POST /api/v1/admin/spec-options`
- `PUT /api/v1/admin/spec-options/{id}`
- `DELETE /api/v1/admin/spec-options/{id}`

规格模型示例：

```ts
interface SpecGroup {
  id: string;
  name: string; // 杯型/温度/糖度/加料
  type: 'single' | 'multiple';
  max_select?: number; // multiple 时生效
  is_required: boolean;
}

interface SpecOption {
  id: string;
  group_id: string;
  name: string; // 大杯/少冰/半糖
  price_delta: number;
  is_default: boolean;
}
```

#### 5.4.5 分类 ↔ 规格组映射

- `GET /api/v1/admin/category-spec-groups?category_id=xxx`
- `PUT /api/v1/admin/category-spec-groups/{category_id}`

请求：

```json
{
  "spec_group_ids": ["group1", "group2", "..."]
}
```

表示该分类默认关联的规格组。

#### 5.4.6 单品 ↔ 规格组映射

- `GET /api/v1/admin/product-spec-groups?product_id=xxx`
- `PUT /api/v1/admin/product-spec-groups/{product_id}`

请求：

```json
{
  "overrides": [
    {
      "spec_group_id": "group1",
      "enabled": true,
      "allowed_option_ids": ["opt1", "opt2"]
    },
    {
      "spec_group_id": "group2",
      "enabled": false
    }
  ]
}
```

此处覆写分类默认配置，实现「某品类默认支持哪些规格组、某杯单独再精细控制」的需求。

#### 5.4.7 可售状态控制

复用已有：

- `PUT /api/v1/admin/inventory/products/{product_id}` 更新商品售罄状态；
- `PUT /api/v1/admin/inventory/spec-options/{option_id}` 更新规格售罄状态。

前端在商品列表/详情页提供开关操作即可。

---

### 5.5 会员与资产模块

#### 5.5.1 会员列表

- `GET /api/v1/admin/members`
- 查询：手机号、昵称、注册时间、最近消费时间等。
- 返回字段必须包含手机号明文（管理端不打码）。

#### 5.5.2 会员详情

- `GET /api/v1/admin/members/{member_id}`
- 返回：
  - 基本信息：昵称、头像、手机号、注册时间等；
  - 统计信息：累计消费金额、订单数、最近消费时间；
  - 当前资产：积分、储值余额、持有优惠券统计。

#### 5.5.3 积分流水

- `GET /api/v1/admin/members/{member_id}/loyalty/transactions`

后端可直接基于现有 `me` 视角接口抽象出 admin 视角。

#### 5.5.4 积分调整

- `POST /api/v1/admin/members/{member_id}/loyalty/adjust`
- 请求：

```json
{
  "delta_points": 100,
  "reason": "延误补偿"
}
```

- 后端：
  - 使用统一服务调整积分；
  - 记录流水；
  - 写审计日志（包括 reason）。

#### 5.5.5 储值相关接口（如开启）

类似积分，增加：

- `GET /api/v1/admin/members/{member_id}/wallet`
- `GET /api/v1/admin/members/{member_id}/wallet/transactions`
- `POST /api/v1/admin/members/{member_id}/wallet/adjust`

---

### 5.6 营销活动模块（优惠券等）

#### 5.6.1 优惠券模板

- `GET /api/v1/admin/coupon-templates`
- `POST /api/v1/admin/coupon-templates`
- `PUT /api/v1/admin/coupon-templates/{id}`
- `DELETE /api/v1/admin/coupon-templates/{id}`

模板包含：类型、规则（满减/折扣/买赠等）、适用范围、有效期、人均限领等。

#### 5.6.2 发券

- `POST /api/v1/admin/coupons/issue`
- 请求：

```json
{
  "template_id": "string",
  "target": {
    "type": "single" | "batch",
    "member_ids": ["id1", "id2"],
    "phones": ["138..."],
    "segment_id": "string (未来支持)"
  },
  "reason": "运营活动补发券"
}
```

发券行为需被审计。

#### 5.6.3 活动效果

- `GET /api/v1/admin/coupon-templates/{id}/stats`
- 返回发放量、使用量、使用率、关联订单 GMV 等。

---

### 5.7 广告与推荐位模块

基于已有 Slot/Creative/Placement 模型：

- `GET /api/v1/admin/ads/slots`
- `POST /api/v1/admin/ads/slots`
- `PUT /api/v1/admin/ads/slots/{id}`
- `DELETE /api/v1/admin/ads/slots/{id}`

- `GET /api/v1/admin/ads/creatives`
- `POST /api/v1/admin/ads/creatives`
- `PUT /api/v1/admin/ads/creatives/{id}`
- `DELETE /api/v1/admin/ads/creatives/{id}`

- `GET /api/v1/admin/ads/placements`
- `POST /api/v1/admin/ads/placements`
- `PUT /api/v1/admin/ads/placements/{id}`
- `DELETE /api/v1/admin/ads/placements/{id}`
- `PUT /api/v1/admin/ads/placements/order` 调整排序

所有变更操作写入审计日志。

---

### 5.8 门店与配置模块

#### 5.8.1 门店信息

- `GET /api/v1/admin/shops`
- `GET /api/v1/admin/shops/{id}`
- `PUT /api/v1/admin/shops/{id}` 更新名称、地址、电话、公告等。

#### 5.8.2 营业状态与功能开关

- `PUT /api/v1/admin/shops/{id}/status`

```json
{
  "is_open": true,
  "today_opening_hours": "09:00-22:00"
}
```

- `PUT /api/v1/admin/config/features/{feature_key}`
  - 打开/关闭优惠券、集点、线上下单等功能；
  - 变更需写审计日志。

---

### 5.9 终端设备管理模块

#### 5.9.1 商家端设备

- `GET /api/v1/admin/devices/merchant`
  - 支持按门店、账号、状态过滤。

- `PUT /api/v1/admin/devices/merchant/{device_id}/approve`
- `PUT /api/v1/admin/devices/merchant/{device_id}/reject`
- `PUT /api/v1/admin/devices/merchant/{device_id}/disable`
- `PUT /api/v1/admin/devices/merchant/{device_id}/unbind`

每个操作请求需要 `reason` 字段，后端写审计日志。

#### 5.9.2 POS 设备

- `GET /api/v1/admin/devices/pos`
- `POST /api/v1/admin/devices/pos`
  - 手动录入 POS 设备（MAC、门店等）；
- `PUT /api/v1/admin/devices/pos/{device_id}/disable`
- `PUT /api/v1/admin/devices/pos/{device_id}/unbind`

后续 POS 首次自注册的 Pending 流程，可通过新增 `POST /api/v1/admin/devices/pos/pending/approve` 等接口实现。

---

### 5.10 Webhook 管理模块

- `GET /api/v1/admin/webhooks`
- `POST /api/v1/admin/webhooks`
- `PUT /api/v1/admin/webhooks/{id}`
- `DELETE /api/v1/admin/webhooks/{id}`

Webhook 配置包含：`endpoint_url`, `secret`, `event_types`, `status`, `retry_policy` 等。配置变更写审计日志。

---

### 5.11 管理员与审计模块

#### 5.11.1 管理员账号

- `GET /api/v1/admin/admins`
- `POST /api/v1/admin/admins`
- `PUT /api/v1/admin/admins/{id}`
- `PUT /api/v1/admin/admins/{id}/disable`
- `PUT /api/v1/admin/admins/{id}/reset-password`

SuperAdmin 才可访问/操作上述接口，操作本身写审计日志。

#### 5.11.2 审计日志查询

- `GET /api/v1/admin/audit-logs`
- 查询参数：
  - `start_time`, `end_time`
  - `operator_id`, `operator_username`
  - `module` / `action`
  - `resource_type`, `resource_id`
  - `ip`

- 响应：
  - 列表 + 分页信息
  - 每条日志含：操作人、时间、IP、模块、action、resource、before/after 摘要、remark。

可增加 `GET /api/v1/admin/audit-logs/export` 提供异步导出能力。

---

## 6. 页面级设计概览

> 这里只给出每个模块的页面结构与主要交互点，详细 UI 以设计稿为准。

### 6.1 登录页

- 路由：`/login`
- 功能：
  - 输入账号、密码；
  - 若后端返回需要 2FA，则显示 OTP 输入框；
  - 登录成功后跳转 `/dashboard`。

### 6.2 首页看板

- 路由：`/dashboard`
- 区域：
  - 指标概览卡片（今日/本周订单数、GMV、退款等）；
  - 趋势图（订单数 & GMV）；
  - Top 商品表；
  - 简要提醒卡片（异常订单数、即将到期的活动等）。

### 6.3 订单列表 & 详情页

- 路由：`/orders`, `/orders/:id`
- 功能：
  - 筛选、搜索、分页；
  - 行操作：查看详情、修改状态、发起退款；
  - 支持按取餐码搜索；
  - 在详情页支持重新生成/修改取餐码（弹框要求填写原因）。

### 6.4 商品 & 菜单管理

- 路由：`/products`, `/products/new`, `/products/:id/edit`
- 列表：
  - 按分类分组展示商品；
  - 支持拖拽排序；
  - 开关上下架、售罄状态。
- 表单：
  - 基本信息、价格、分类选择、规格组配置；
  - 支持选择继承分类默认规格组并进行覆写。
- Excel 导入：
  - 入口按钮：`批量导入`；
  - 模板下载 + 文件上传 + 校验结果预览。

### 6.5 会员 & 资产

- 路由：`/members`, `/members/:id`
- 列表：
  - 显示手机号明文；
  - 支持按手机号/昵称搜索。
- 详情：
  - 显示资产、订单列表、积分流水；
  - 按钮：`调整积分`、`调整储值`（权限控制）。

### 6.6 营销活动

- 路由：`/marketing/coupons`
- 功能：
  - 查看所有优惠券模板；
  - 创建/编辑模板；
  - 为指定用户发券；
  - 查看活动效果。

### 6.7 广告 & 推荐位

- 路由：`/ads`
- 功能：
  - 管理广告位、素材与投放；
  - 调整排序；
  - 配置跳转链接。

### 6.8 门店配置

- 路由：`/shop/settings`
- 功能：
  - 编辑门店信息；
  - 调整营业时间；
  - 配置功能开关。

### 6.9 设备管理

- 路由：`/devices/merchant`, `/devices/pos`
- 功能：
  - 查看设备列表；
  - 审批 pending 设备；
  - 禁用/解绑设备；
  - 强制下线设备。

### 6.10 Webhook 管理

- 路由：`/webhooks`
- 功能：
  - 管理 Webhook 配置；
  - 查看投递日志（可在后续版本）。

### 6.11 系统与审计

- 路由：`/system/admins`, `/system/audit`
- 功能：
  - 管理管理员账号；
  - 查询审计日志、导出。

---

## 7. 非功能 & 开发约定

### 7.1 性能

- 列表页面默认分页大小建议为 20/50；
- 大数据导出采用异步方式，避免阻塞请求；
- React Query 对数据进行缓存，避免重复请求。

### 7.2 错误处理

- 所有 API 错误需通过全局拦截器提示用户：
  - 鉴权错误：跳转登录；
  - 权限不足：提示无权限，并可跳转 403 页面；
  - 业务错误：使用 `message.error`/`notification.error` 提示具体信息。

### 7.3 日志与审计协作

- 前端负责：
  - 在需要备注的操作（积分调整、退款、取餐码修改等）确保 `reason` 字段必填；
  - 在调用接口时附带必要上下文（如当前订单 ID、设备 ID 等）。

- 后端负责：
  - 在所有写操作的 Handler 中统一调用审计日志写入模块；
  - 确保审计日志 append-only 且包含完整信息。

---

本 develop.md 作为 Web 管理端开发与管理 API 扩展的基线文档，后续随着业务演进补充新的模块与接口时，应保持相同风格与结构进行增修。

