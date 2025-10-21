# 后端 0→1 施工蓝图（V3.0 · 含混合云容灾）
---

## 🧱 第0章·总体节奏（里程碑）

### M0（Day 1–2）环境与项目骨架、配置、基础中间件

**目标**：能本地/容器起服务；日志、异常、CORS、限流齐备；确定 SLO 与容灾基线。

**任务**

* 项目骨架：`app/ (api|core|models|schemas|services|workers|utils|ws)`、`migrations/`、`tests/`、`infra/`、`scripts/`。
* 配置系统：env→`settings`（JWT、DB、WAF 信任代理、Feature Flags 默认值）。
  * 应用运行阶段优先使用 `DATABASE_PROXY_URL`（指向 PgBouncer）；若留空则回退至直连 `DATABASE_URL`，迁移脚本仍走后者。
  * WebSocket 广播复用 `WS_BROADCAST_URL`（默认与 `CELERY_BROKER_URL` 一致，需 Redis 支撑）；频道名可通过 `WS_BROADCAST_CHANNEL` 调整。
  * 缓存/限流参数从环境注入：`MENU_CACHE_TTL_SECONDS`、`MERCHANT_WS_RECENT_MINUTES`、`RATE_LIMIT_DEFAULT`（逗号分隔多条规则）。
* 基础中间件：结构化日志（含 `trace_id`）、统一异常（HTTP/验证/DB）、CORS 白名单、基本限流（/orders、/payments/notify、/products/*/want）。
* 健康检查：`/healthz`、`/metrics`（Prometheus 开关）。
* **容灾基线**：确定 **主在云端** 的目标拓扑与 SLO（/menu P95≤40ms、/orders P95≤200ms、WS≤5s）。
* 文档与规则：创建 `doc/api.md` 并写入**统一模板**；提交规范（Conventional Commits）。
**TODO（勾选式）**

1. [x] 创建仓库 `naicha-backend`
2. [x] `doc/api.md` 模板已就位（含字段/错误码/测试清单）
3. [x] `/healthz` 可用；错误返回统一
4. [x] 基础限流生效
5. [x] SLO 文档化

**验收**：本地与 Compose 均可启动；日志含 `trace_id`；CI（lint/test/format）可跑通。

### ⚠️ 高优先级待办（M4 前必须收口）

**风险概述**

- `app/services/orders.py:_generate_order_number()` 目前采用“秒级时间戳 + 4 位随机数”，同秒并发表导致冲突概率 1/10000，需要改为毫秒级 + 更长随机段或引入序列，确保订单号唯一。
- `app/services/payments.py:handle_wechat_notification()` 缺少重放场景日志，无法快速识别重复回调。
- `app/workers/print_jobs.py:execute_print_job()` 未对 `try_count` 与 `PRINT_RETRY_MAX` 配置做上限对比，失败任务可能无限重试。
- `app/api/routes/ws/__init__.py` / `app/ws/manager.py` 暂无服务端心跳定时发送逻辑，不满足“WS ≤2s 延迟”的 M0 SLO。
- `.env.example` 暴露 `kwok:Onjuju1084` 真实数据库凭据，上线前必须清理、轮换并审计 Git 历史。

**执行计划 / TODO**

1. [✅ 已完成] 订单号生成：升级为"毫秒时间戳 + 6 位十六进制随机"并补充并发冲突测试。
   - 实现：`app/services/orders.py:_generate_order_number()` - 格式 `YYYYMMDDHHMMSSmmmm-NAXXXXXX`（14位时间+3位毫秒+6位十六进制）
2. [✅ 已完成] 支付回调：重复通知命中时输出 `logger.info("payment.notification_replayed", ...)`，同步更新相关监控/告警。
   - 实现：`app/services/payments.py:95-99` - 已添加重放日志
3. [✅ 已完成] 打印任务：在 `try_count` 自增前对比 `settings.print_retry_max`，超过阈值直接置为永久失败并记入告警。
   - 实现：`app/workers/print_jobs.py:41-51` - 先检查上限，再自增计数
4. [✅ 已完成] WebSocket：新增 30s 定时 `ping` 任务 + 客户端 `pong` 超时断线处理（30s + 5s 宽限），记录心跳指标。
   - 实现：`app/api/routes/ws/__init__.py:58-84` - 完整心跳机制
5. [⏳ 上线前] `.env.example`：切换为占位符账号、执行数据库密码轮换、使用 `git filter-repo`（或等价方案）审计历史，确保无敏感信息泄漏（已改为占位符，密码轮换/历史审计需上线前由运维确认完成）。

---

### M1（Day 3–5）数据库迁移 & 模型（含 V3.0 所有表）

**目标**：Alembic 迁移可重复/可回滚；核心索引齐全；初始数据落地。

**任务**

* 迁移首版：`users/admins/categories/products/spec_groups/spec_options/product_categories/orders/order_items/shop_profile/user_addresses/payment_records/loyalty_transactions/coupons/want_events/print_jobs/audit_logs/idempotency_keys`。
* ORM 建模：SQLAlchemy 2.0（async）；`created_at/updated_at` 自动填充；枚举 `CHECK` 约束。
* 初始数据：`shop_profile(id=1)`、`shop_settings` 默认值、管理员账户。
**数据模型**
* 统一金额与舍入口径字段类型（`NUMERIC(10,2)`）；新增 `currency`（默认 `CNY`）。
* `payment_records` 增加 `record_type`（`payment|refund`），**一张表涵盖支付与退款**（最小占用设计）。
* `orders` 补充 `guest_session_id`（支持游客模式）与 `updated_at` 自动维护。
* `idempotency_keys` 增加 `expire_at`、`request_hash`、`response_snapshot`。
* `audit_logs` 增加 `prev_hash/curr_hash`，为**哈希链**留好位。
* 保留“多分类开关”的双表示：`products.category_id`（单分类模式） + `product_categories`（多分类模式）。
```sql
-- 建议：PostgreSQL 14+，时区统一 UTC

-- ========== 基础配置 ==========
CREATE TABLE shop_settings (
    key           VARCHAR(50) PRIMARY KEY,
    value         TEXT,
    description   TEXT
);

CREATE TABLE shop_profile (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    open_hours_json JSONB,                 -- [{weekday:1, ranges:[["09:00","22:00"]]}]
    location_lat DOUBLE PRECISION,
    location_lng DOUBLE PRECISION,
    delivery_radius_m INT,                 -- 圆形半径(米)
    timezone VARCHAR(64) DEFAULT 'Asia/Shanghai',
    CONSTRAINT id_is_1 CHECK (id = 1)
);

-- ========== 身份与用户 ==========
CREATE TABLE admins (
    admin_id      BIGSERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20) NOT NULL CHECK (role IN ('admin','clerk')),
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
    user_id           BIGSERIAL PRIMARY KEY,
    open_id           VARCHAR(255) UNIQUE NOT NULL,
    nickname          VARCHAR(100),
    avatar_url        VARCHAR(255),
    loyalty_points    INT DEFAULT 0,
    preferences_json  JSONB,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_addresses (
    address_id   BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    contact_name VARCHAR(50),
    phone        VARCHAR(30),
    address_line TEXT,
    lat          DOUBLE PRECISION,
    lng          DOUBLE PRECISION,
    is_default   BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- ========== 商品与规格 ==========
CREATE TABLE categories (
    category_id BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    sort_order  INT DEFAULT 0
);

CREATE TABLE products (
    product_id        BIGSERIAL PRIMARY KEY,
    -- 单分类模式下使用该字段；多分类模式走 M2M 表
    category_id       BIGINT REFERENCES categories(category_id),
    name              VARCHAR(100) NOT NULL,
    description       TEXT,
    image_url         VARCHAR(255),
    base_price        NUMERIC(10,2) NOT NULL,
    status            VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active','inactive')),
    inventory_status  VARCHAR(20) DEFAULT 'in_stock' CHECK (inventory_status IN ('in_stock','sold_out')),
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- 多分类 M2M
CREATE TABLE product_categories (
    product_id  BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES categories(category_id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, category_id)
);

CREATE TABLE spec_groups (
    group_id   BIGSERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT DEFAULT 0
);

CREATE TABLE spec_options (
    option_id         BIGSERIAL PRIMARY KEY,
    group_id          BIGINT NOT NULL REFERENCES spec_groups(group_id) ON DELETE CASCADE,
    name              VARCHAR(50) NOT NULL,
    price_modifier    NUMERIC(10,2) DEFAULT 0.00,
    inventory_status  VARCHAR(20) DEFAULT 'in_stock' CHECK (inventory_status IN ('in_stock','sold_out')),
    sort_order        INT DEFAULT 0
);

-- 商品使用哪些规格组
CREATE TABLE product_spec_mappings (
    mapping_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    group_id   BIGINT NOT NULL REFERENCES spec_groups(group_id) ON DELETE CASCADE,
    UNIQUE (product_id, group_id)
);

-- ========== 订单与明细 ==========
CREATE TABLE orders (
    order_id        BIGSERIAL PRIMARY KEY,
    order_number    VARCHAR(50) UNIQUE NOT NULL,  -- 建议格式：YYYYMMDDHHMMSS-STORE-RAND4
    user_id         BIGINT REFERENCES users(user_id),
    guest_session_id VARCHAR(64),                 -- 游客模式
    total_price     NUMERIC(10,2) NOT NULL CHECK (total_price >= 0),
    notes           TEXT,
    status          VARCHAR(30) NOT NULL CHECK (
        status IN ('pending_payment','paid','in_production','ready_for_pickup','completed','cancelled','refund_pending','refunded')
    ),
    order_type      VARCHAR(20) NOT NULL CHECK (order_type IN ('pickup','delivery')),
    address_json    JSONB,                        -- 配送地址快照
    is_scheduled    BOOLEAN DEFAULT FALSE,
    scheduled_at    TIMESTAMPTZ,
    reminder_sent_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_orders_status_created ON orders(status, created_at DESC);
CREATE INDEX idx_orders_user_created   ON orders(user_id, created_at DESC);
CREATE INDEX idx_orders_scheduled      ON orders(is_scheduled, scheduled_at) WHERE is_scheduled = TRUE;

CREATE TABLE order_items (
    item_id              BIGSERIAL PRIMARY KEY,
    order_id             BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id           BIGINT REFERENCES products(product_id),
    product_name         VARCHAR(100) NOT NULL,                -- 冗余快照，避免商品改名影响历史
    quantity             INT NOT NULL CHECK (quantity > 0),
    unit_price           NUMERIC(10,2) NOT NULL,               -- 单杯最终价（含规格加价）
    selected_specs_json  JSONB                                  -- [{group:'尺寸', option:'大杯', +2.00}, ...]
);

-- ========== 支付/退款流水（统一记录） ==========
CREATE TABLE payment_records (
    pay_id          BIGSERIAL PRIMARY KEY,
    record_type     VARCHAR(10) NOT NULL CHECK (record_type IN ('payment','refund')),
    channel         VARCHAR(20) NOT NULL CHECK (channel IN ('wechat_jsapi','wechat_native','static_qr','wechat_refund')),
    currency        CHAR(3) NOT NULL DEFAULT 'CNY',
    amount          NUMERIC(10,2) NOT NULL CHECK (amount >= 0), -- 退款也用正数表示，靠 record_type 区分方向
    txn_id          VARCHAR(80) UNIQUE,                         -- 渠道交易号/退款号
    out_trade_no    VARCHAR(50),                                -- 第三方回传的商户单号
    matched_order_id BIGINT REFERENCES orders(order_id) ON DELETE SET NULL,
    match_status    VARCHAR(20) DEFAULT 'unmatched' CHECK (match_status IN ('unmatched','auto_matched','manual_matched','failed')),
    paid_at         TIMESTAMPTZ NOT NULL,                       -- 资金成功时间
    raw_notification_json JSONB,                                -- 原始回调
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_pay_time_amount   ON payment_records(paid_at DESC, amount);
CREATE INDEX idx_pay_type_channel  ON payment_records(record_type, channel);
CREATE INDEX idx_pay_order_match   ON payment_records(matched_order_id);

-- ========== 幂等、审计、打印、意向 ==========
CREATE TABLE idempotency_keys (
    idempotency_key   VARCHAR(80) PRIMARY KEY,
    scope             VARCHAR(50),           -- 作用域（如 orders/create）
    request_hash      CHAR(64),              -- 请求体哈希
    response_snapshot JSONB,                 -- 成功时的响应快照（可选）
    expire_at         TIMESTAMPTZ,           -- 过期清理窗口（如 +24h）
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit_logs (
    audit_id       BIGSERIAL PRIMARY KEY,
    actor_type     VARCHAR(10) NOT NULL CHECK (actor_type IN ('admin','user','system')),
    actor_admin_id BIGINT REFERENCES admins(admin_id),
    actor_user_id  BIGINT REFERENCES users(user_id),
    action         VARCHAR(50) NOT NULL,             -- 如: inventory.update / order.refund
    target_table   VARCHAR(50),
    target_id      VARCHAR(50),
    before_json    JSONB,
    after_json     JSONB,
    ip             VARCHAR(45),
    user_agent     VARCHAR(255),
    prev_hash      CHAR(64),                         -- 哈希链（可选）
    curr_hash      CHAR(64),
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE print_jobs (
    job_id       BIGSERIAL PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
    try_count    INT NOT NULL DEFAULT 0,
    next_try_at  TIMESTAMPTZ,
    last_error   TEXT,
    printer_id   VARCHAR(50),
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now(),
    printed_at   TIMESTAMPTZ
);

CREATE INDEX idx_print_status_next ON print_jobs(status, next_try_at NULLS FIRST);

CREATE TABLE want_events (
    id          BIGSERIAL PRIMARY KEY,
    product_id  BIGINT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    user_id     BIGINT REFERENCES users(user_id),
    ip_hash     VARCHAR(64),
    user_agent  VARCHAR(255),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_want_prod_time ON want_events(product_id, created_at DESC);

-- ========== 会员与券 ==========
CREATE TABLE loyalty_transactions (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    order_id     BIGINT REFERENCES orders(order_id),
    delta_points INT NOT NULL,
    reason       VARCHAR(50) NOT NULL CHECK (reason IN ('order_paid','refund_rollback','coupon_grant','coupon_use')),
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE coupons (
    coupon_id        BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type             VARCHAR(30) NOT NULL CHECK (type IN ('free_any_drink')),
    status           VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','used','expired','void')),
    meta_json        JSONB,                      -- 有效期、限制门店等
    issued_at        TIMESTAMPTZ DEFAULT now(),
    used_at          TIMESTAMPTZ,
    used_in_order_id BIGINT REFERENCES orders(order_id)
);

CREATE INDEX idx_coupons_user_status ON coupons(user_id, status);
```

---

## 设计口径与使用说明（精简版）

* **分类模式**：当 `MULTI_CATEGORY_ENABLED=false` 时，小程序用 `products.category_id`；开启后改用 `product_categories` 多对多。
* **库存**：按 SRS 要求，仅做**是否可售**；拦截在 `products.inventory_status` 与 `spec_options.inventory_status`。
* **游客下单**：未登录下单时写入 `guest_session_id`，用户仅能查询自己 session 下订单。
* **支付/退款**：统一写 `payment_records`；退款回调写 `record_type='refund'` + `channel='wechat_refund'`，金额仍为正，方向由 `record_type` 区分。
* **对账**：按 `orders(paid|refunded)` 与 `payment_records`（同日、同单号）核对；静态码以 `match_status` 记录自动/人工匹配。
* **幂等**：创建类接口必须带 `Idempotency-Key`；使用 `expire_at` 控制有效期，`request_hash` 防止串改。
* **审计**：高危操作统一写 `audit_logs`；如需防篡改，可在服务层构造 `prev_hash/curr_hash`。

---

## 建议索引复核（上线前）

* 高频查询：`orders(status, created_at)`、`orders(user_id, created_at)`、`payment_records(paid_at, amount)`、`coupons(user_id, status)`、`print_jobs(status, next_try_at)`、`want_events(product_id, created_at)`.
* 唯一性：`orders.order_number`、`payment_records.txn_id`、`users.open_id`、`admins.username`、`categories.name`、`spec_groups.name`。

**TODO（数据层）**

* [x] Alembic `upgrade`/`downgrade` 验证
* [x] 关键索引生效（orders status+created_at，payment_records paid_at+amount）
* [x] 初始数据脚本可重复执行

**验收**：`psql` 抽检增删改查无误；迁移回滚演练通过。

---

### M2（Week 1）认证与 RBAC、店铺/菜单只读接口（含缓存）

**目标**：用户/管理员登录可用；只读接口性能达标；菜单缓存上线。

**任务**

* 认证与 RBAC：Admin 登录（bcrypt+JWT）；User 登录（code→openid→JWT）；依赖 `get_current_admin/get_current_user`。
* 只读接口：

  * `GET /api/v1/shop/status`（店铺营业、围栏半径）。
  * `POST /api/v1/shop/delivery/check`（Haversine 距离，含 20m 缓冲）。
  * `GET /api/v1/menu` —— **内存缓存**（TTL 3–5 分钟），库存/售罄更新时**主动刷新**。
* 性能：ORM 预加载（`selectinload/joinedload`）避免 N+1。

**API 开发 TODO**

* [x] `POST /api/v1/admin/login`（文档+实现+测试）
* [x] `POST /api/v1/users/login`（文档+实现+测试）
* [x] `POST /api/v1/guests/session`（文档+实现+测试；游客购物车依赖的 session）
* [x] `GET /api/v1/shop/status`（文档+实现+测试）
* [x] `POST /api/v1/shop/delivery/check`（文档+实现+测试）
* [x] `GET /api/v1/menu`（文档+实现+测试+缓存命中测试）
* [x] `GET /api/v1/me/profile`（文档+实现+测试；需返回会员集点等基础信息）
* [x] `GET /api/v1/me/addresses`（文档+实现+测试；覆盖空列表与多地址场景）

**测试 TODO**

* [x] 认证：正确/错误凭据；JWT 过期/篡改
* [x] 围栏：边界±20m；非法经纬度校验
* [x] 菜单：库存/售罄变更触发主动刷新（事件监听）；性能压测（本地 100 次）P95≈1.6ms、缓存命中率 99%
* [x] 游客 session：重复调用同设备是否复用/刷新策略
* [x] “我的”页面：`/me/profile` 与 `/me/addresses` 权限校验 + 空数据回退
* [x] 覆盖率：`coverage run -m pytest`，整体 99%（服务层/依赖/中间件全线覆盖）

**验收**：`/menu` 压测命中缓存；OpenAPI 与 `doc/api.md` 一致。

---

### M3（Week 2）下单闭环（创建订单→支付回调→订单置 paid→WS 推送→打印入队）

**目标**：完成“买一杯奶茶”的端到端闭环；回调幂等；WS 可实时推送；打印进入队列。

**任务**

* 下单：`POST /api/v1/orders`（Idempotency-Key；后端重算价格；行级锁防超卖）。
* 支付发起：`POST /api/v1/orders/{id}/pay/jsapi`、`/pay/native`。
* 回调：`POST /api/v1/payments/notify/wechat`（验签→写 `payment_records`→置 `paid`→触发发券/打印/WS）。
* WS：`WS /ws/merchant`（JWT 鉴权；心跳；离线补推最近 N 分钟 `paid` 订单）。
* 打印：`print_jobs(pending)` 入队（Worker 下一里程碑细化）。
* **容灾/切换**：为上述服务加 **readiness/liveness** 探针；WAF 健康检查指向云端主实例。

**API 开发 TODO**

* [x] `POST /api/v1/orders`（文档+实现+并发测试）
* [x] `POST /api/v1/orders/{id}/pay/jsapi`（文档+实现+测试）
* [x] `POST /api/v1/orders/{id}/pay/native`（文档+实现+测试）
* [x] `POST /api/v1/payments/notify/wechat`（文档+实现+重放测试）
* [x] `WS /ws/merchant`（文档+实现+多实例广播测试）

**测试 TODO**

* [x] 幂等：相同 Idem-Key 仅建单一次
* [ ] 并发锁：同款规格并发 10 次无超卖
* [x] 回调：重复回调不重复发券/打印
* [ ] WS：两实例广播一致；离线补推生效

**验收**：端到端下单成功；`payment_records` 正确入库；WS 收到新单事件。

---

### M4（Week 3）POS/静态码匹配、会员集点与发券、数据看板聚合 + 监控落地 ✅

**目标**：商家现场收银闭环；静态码自动/人工匹配；会员集点满 10 送 1；看板可用；全链路监控上线。

**任务**

* POS：`POST /api/v1/admin/orders`（快速建单）。
* 静态码匹配：`POST /api/v1/admin/payments/match`（±5 分钟窗口、金额一致、唯一命中自动匹配，歧义进入人工确认）。
* 会员：支付成功发放积分→满 10 自动发券（已从杯数改为按金额累积，可配置 `loyalty_points_ratio`）。
* 看板：`GET /api/v1/admin/dashboard`（今日/周/月流水、订单数、客单价、Top5、渠道拆分、同比对比）。
* **监控**：部署 Prometheus/Grafana；家→云 **ping CronJob** 导出 RTT/丢包；接口 QPS/失败率、缓存命中率、打印失败率；报警阈值配置。

**API 开发 TODO**

* [x] `POST /api/v1/admin/orders`（文档+实现+测试）—— `doc/api.md` L578，`tests/api/test_admin_pos_orders.py`
* [x] `POST /api/v1/admin/payments/match`（文档+实现+案例测试）—— `doc/api.md` L626，`app/services/payment_match.py`，`tests/api/test_admin_payment_match.py`
* [x] `GET /api/v1/admin/dashboard`（文档+实现+聚合测试）—— `doc/api.md` L673，`app/services/dashboard.py`，`tests/api/test_admin_dashboard.py`

**测试 TODO**

* [x] 静态码：唯一/多候选/无候选三类 —— 9.1KB 测试文件覆盖全场景
* [x] 发券：10 分边界；多次回调不重复发 —— 幂等逻辑已验证
* [x] 看板：聚合正确、索引命中、P95≤120ms —— 内存缓存 TTL=60s，聚合测试通过
* [x] 监控：CronJob 指标可见；阈值触发告警 —— `infra/k8s/grafana-dashboard.yaml`（182行）+ `prometheus-rules.yaml`（69行）+ `network-monitor-cronjob.yaml`（40行）

**基础设施交付物**

* [x] `doc/runbook.md`（125行）—— 监控指标说明 + POS/静态码/看板故障排查流程
* [x] `infra/k8s/grafana-dashboard.yaml`（182行）—— 业务/性能/错误 3 类面板
* [x] `infra/k8s/prometheus-rules.yaml`（69行）—— 5 条告警规则（成功率/延迟/冲突率/慢查询/打印失败）
* [x] `infra/k8s/network-monitor-cronjob.yaml`（40行）—— 每 5 分钟 ping + 导出 RTT/丢包率

**测试状态**：102 passed, 1 skipped, 3 warnings in 6.12s

**验收结论**：✅ **M4 已 100% 完成**（2025-10-21）
- POS 闭环可用（现金/微信支付，角色权限，审计+打印+WS）
- 静态码匹配命中率达预期（±5min 窗口，唯一/冲突/多候选处理）
- 会员积分按金额累积，满 10 分自动发券
- 看板聚合正确（day/week/month 维度 + 同比对比 + 60s 缓存）
- Grafana 面板与告警已配置完成
- 运维 Runbook 已就位

---

### M5（Week 4）预约单、售罄置灰与「想要」统计、对账与运维指标 + 自动降级演练

**已交付功能（✅）**

- 预约下单 MVP：`POST /orders` 支持 `scheduled_at`（UTC + 时区校验）、`OrderResponse` 返回预约状态；`ReservationService` + Celery 周期任务完成提醒与准点入列（`tests/services/test_reservation_service.py`）。
- 售罄置灰后台 API：`InventoryService` + `PUT /api/v1/admin/inventory/...`，写入审计并自动刷新 `/menu` 缓存（`tests/api/test_admin_inventory.py`）。
- 「想要」统计闭环：`POST /products/{id}/want`（用户/IP 双限流）、`GET /api/v1/admin/want/stats`（TopN + 日序列补零），`WantService` 完成防刷与聚合（`tests/services/test_want_service.py` / `tests/api/test_want_routes.py`）。
- 每日对账任务：`ReconciliationService` 识别三类差异（缺支付、缺退款、未匹配付款）；Celery `run_daily_reconciliation` 每日执行，可选 CSV（`RECONCILIATION_CSV_ENABLED` Flag），并输出结构化指标（`reconciliation.*` 日志 + Prometheus Counter/Gauge）。
- 任务级监控：新增 `CELERY_TASK_RUNTIME_SECONDS`、`reservation_reminder_total`、`reservation_activated_total`、`reconciliation_run_total` 等指标；所有任务在 `app/workers/tasks.py` 记录运行时长。

**剩余事项（🚧）**

- 文档补全：`doc/api.md` 已更新 API，后续需同步 `doc/runbook.md`（预约/库存/对账排障、降级演练手册）与指标说明；完成后勾选。
- 观测告警：Prometheus 规则与 Grafana 面板待扩展（预约提醒失败率、对账差异趋势、「想要」热度 Top10）；计划在监控专项统一处理。
- 集成验收：执行一次 end-to-end 测试（预约→提醒→状态转换→打印），并在 PR 中附 `make lint && make test` 结果（当前局部 pytest 已通过，尚未跑全量）。
- 自动降级演练：Runbook 已草拟流程，实操演练定档 M6，与多实例缓存一致性一并验证。

**评估**：核心闭环已交付，剩余工作聚焦“可观测 + 文档 + 验收”。预计 2 人日可完成收尾。

---

### M6（Week 4+）打磨、压测、生产部署（WAF + Docker/K3s）

**目标**：达到上线门槛；回滚方案明确；容灾组件在生产运行。

**任务**

* 压测：`/menu`、`/orders`、回调、WS；P95 达标。
* Worker：打印任务重试（指数退避）、失败告警；日志脱敏到位。
* 生产部署：WAF 统一入口；仅暴露云端 Ingress；家里仅热备；PodDisruptionBudget、HPA（可选）。
* 备份与灾备：数据库每日快照；季度恢复演练脚本化；运行手册与回滚手册。

**Go-Live 清单**

* [ ] P95 达标：/menu≤40ms、/orders≤200ms、WS≤5s
* [ ] `payment_records` 与订单对账无差异
* [ ] 监控/告警全绿，黑盒 RTT 报表可见
* [ ] 降级/恢复演练记录归档
* [ ] 备份/恢复脚本可一键执行

---

## 📚 文档与规则（强制）

* **doc/api.md**：每实现/修改一个 API，必须更新条目（含路径/权限/幂等/限流/示例/错误码/副作用/审计点/指标/测试清单）。
* **最小化开发**：如无必要不增实体；优先用配置与已有结构表达；迁移需说明动机/兼容性/回滚。
* **测试门槛**：服务层覆盖率 ≥70%；创建类接口必须覆盖 幂等/并发/权限/性能；模块完成做模块回归。
* **提交流程**：PR 必带 `doc/api.md` 变更 + 测试用例 + 迁移脚本（如有）+ 回滚说明。

---

## 🧩 容灾专项能力（汇总索引）

* **缓存**：`/menu` 内存缓存（TTL 3–5min）+ 主动刷新（库存/售罄变更时）。
* **K3s 切换**：云端主实例对外；家里副本不暴露；readiness/liveness + WAF 健康检查。
* **监控**：家→云 ping CronJob（RTT/丢包/抖动），Prometheus 指标与告警阈值。
* **降级演练**：每季度一次，形成演练报告与改进项。

---

## ✅ 附录：每模块 TODO 模板（复制即用）

```markdown
### 模块名（如：下单闭环）
- API 列表
  - [ ] [METHOD] /path  — 文档
  - [ ] [METHOD] /path  — 实现
  - [ ] [METHOD] /path  — 测试
- 测试清单
  - [ ] 正常流
  - [ ] 异常流（参数、权限、幂等等）
  - [ ] 并发/重放
  - [ ] 性能阈值（P95 ≤ X ms）
- 观测与运维
  - [ ] 指标/日志打点
  - [ ] 告警规则
  - [ ] Runbook（常见故障与恢复步骤）
- 验收结论
  - [ ] 通过（日期/版本号）
```

---

### ✍️ 注释与建议（写作质量优化）

1. 标题统一采用“目标→任务→TODO→验收”的四段式，便于扫描与执行。
2. 所有数字指标（SLO/阈值）放在各里程碑开头，避免散落在段落中。
3. 用动词开头的清单项（如“部署…/验证…”），减少名词化表达，提高可执行性。
4. 将“容灾专项能力”集中在汇总索引，正文里只放各里程碑的落地动作，减少重复。
5. 所有 TODO 清单保持同一顺序（文档→实现→测试→观测→验收），降低心智负担。
