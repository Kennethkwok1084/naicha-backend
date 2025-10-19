# 智能奶茶档口系统 · 后端（V3.0）


## 目录

* [项目简介](#项目简介)
* [系统架构](#系统架构)
* [核心特性](#核心特性)
* [快速开始（本地/容器）](#快速开始本地容器)
* [环境变量](#环境变量)
* [运行与常用脚本](#运行与常用脚本)
* [数据库迁移](#数据库迁移)
* [API 总览](#api-总览)
* [缓存与性能](#缓存与性能)
* [安全与鉴权](#安全与鉴权)
* [可观测性](#可观测性)
* [部署（K3s 混合云）](#部署k3s-混合云)
* [备份与容灾演练](#备份与容灾演练)
* [SLO 与容量规划](#slo-与容量规划)
* [开发规范](#开发规范)
* [目录结构](#目录结构)
* [路线图](#路线图)
* [许可证](#许可证)

---

## 项目简介

本仓库是“智能奶茶档口系统”的**后端服务**，基于 **FastAPI** 构建，提供：

* 顾客端小程序 API（点单、支付、订单）
* 商家端 API & WebSocket（实时接单、打印、状态流转）
* Web 管理后台所需的配置与数据看板接口
* 会员集点、优惠券、售罄/想要、预约单等扩展能力

配套的 **V3.0 终极开发规范** 已固化到实现细节（状态机、幂等、审计、支付流水等）。

---

## 系统架构

* **应用**：FastAPI（Uvicorn/Gunicorn，异步 IO）
* **数据库**：PostgreSQL（云端主库） + **PgBouncer** 连接池
* **缓存**：应用内存缓存（`/menu` 等只读热点数据）
* **实时**：WebSocket（商家端接单/推送）
* **部署**：K3s（云端控制面 + 家庭工作节点），雷池 WAF 统一对外
* **监控**：Prometheus + Grafana，黑盒网络质量监控（家→云 ping）

---

## 核心特性

* 严格的**分层架构**：API Router → Service → Model/Repo
* 完整**订单状态机**：`pending_payment → paid → in_production → ready_for_pickup → completed`（含退款）
* **价格后端重算**、**并发库存校验**、**幂等键**、**审计日志**
* **支付流水**记录与**静态码匹配**、打印任务队列（失败重试）
* **会员集点**（满10送1）与**优惠券**闭环
* **预约单**& **售罄/想要**能力按开关启用

---

## 快速开始（本地/容器）

### 方式 A：Docker Compose（推荐）

```bash
cp .env.example .env
# 按需修改 .env（数据库密码、JWT 密钥等）
docker compose up -d --build
```

启动后：

* API: `http://localhost:8000`
* 文档: `http://localhost:8000/docs`

### 方式 B：本地运行（需要本地 Postgres/PgBouncer）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## 环境变量

见 `.env.example`（本地开发示例，生产环境请通过 Secret 注入）：

```
APP_ENV=dev
SECRET_KEY=__GENERATE_ME__
JWT_EXPIRE_MINUTES=43200
DATABASE_URL=postgresql+asyncpg://user:pass@pgbouncer:6432/naicha
DATABASE_PROXY_URL=postgresql+asyncpg://user:pass@pgbouncer:6432/naicha
PGBOUNCER_HOST=pgbouncer
PGBOUNCER_PORT=6432
PROMETHEUS_ENABLED=true
WAF_TRUST_PROXY=true
# Feature Flags
MULTI_CATEGORY_ENABLED=true
RESERVATION_ENABLED=false
WANT_ENABLED=true
SOLDOUT_STYLE=hide  # hide|disabled
RESERVATION_REMINDER_MINUTES=15
STATIC_MATCH_TIME_WINDOW_MIN=5
DELIVERY_RADIUS_M=1500
PRINT_RETRY_MAX=5
MENU_CACHE_TTL_SECONDS=240
MERCHANT_WS_RECENT_MINUTES=5
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
CELERY_DEFAULT_QUEUE=default
PRINT_JOB_QUEUE_NAME=print_jobs
PRINTER_WEBHOOK_URL=
PRINTER_WEBHOOK_TOKEN=
PRINTER_TIMEOUT_SECONDS=5
WS_BROADCAST_URL=redis://redis:6379/0
WS_BROADCAST_CHANNEL=ws:merchant:broadcast
RATE_LIMIT_DEFAULT=300/minute
```

> ⚠️ **生产环境要求**：`SECRET_KEY`、`DATABASE_URL`/`DATABASE_PROXY_URL`、`CELERY_*`、`WS_BROADCAST_*`、`PRINTER_*` 等敏感配置必须来自 K8s Secret、Vault 或云厂商密钥管控，禁止在镜像与 Git 仓库中出现明文。

---

### 生产部署要点

- **准备 Secret**：部署前执行一次 `kubectl create secret generic naicha-api-secrets --from-literal=...`，包含数据库、Redis、打印服务等敏感变量（具体命令见 `infra/README.md`）。
- **基础服务**：确保 Redis 与 PgBouncer 可用，并与 `CELERY_*`、`WS_BROADCAST_URL`、`DATABASE_PROXY_URL` 对应。
- **发布流程**：`kubectl apply -f infra/k8s/deployment.yaml`、`infra/k8s/service.yaml` 与 `infra/k8s/worker-deployment.yaml`，再通过 `kubectl rollout restart` 滚动更新 API 与 Worker。

---

## 运行与常用脚本

```bash
# 代码质量
make fmt       # 格式化（black/isort/ruff）
make lint      # 静态检查
make test      # 单元/集成测试

# 数据库
make migrate   # 生成迁移
make updb      # 应用迁移（alembic upgrade head）

# 本地启动
make dev       # uvicorn --reload
make worker    # Celery worker（处理打印等后台任务）
```

---

## 数据库迁移

* 使用 **Alembic**；首版迁移已包含 **V3.0 全量表结构**（订单/支付流水/打印作业/审计/幂等等）。
* 新增表或字段：`alembic revision --autogenerate -m "feat: xxx"` → `alembic upgrade head`

---

## API 总览

> 详细见 `/docs`（OpenAPI）。以下列出核心端点：

### 公共/顾客侧

* `GET  /api/v1/shop/status` — 店铺状态
* `POST /api/v1/shop/delivery/check` — 围栏校验
* `GET  /api/v1/menu` — 菜单（内存缓存）
* `POST /api/v1/orders` — 创建订单（需用户 JWT；支持券/预约）
* `GET  /api/v1/orders` — 我的订单列表
* `POST /api/v1/orders/{id}/pay/jsapi` — 小程序支付参数
* `POST /api/v1/payments/notify/wechat` — 支付回调（Webhook）

### 商家/管理侧（需 Admin/Clerk 角色）

* `POST /api/v1/admin/login` — 登录获取JWT
* `GET  /api/v1/admin/orders` — 订单列表（筛选）
* `PUT  /api/v1/admin/orders/{id}/status` — 流转状态
* `POST /api/v1/admin/orders/{id}/print` — 重打小票
* `POST /api/v1/admin/payments/match` — 静态码匹配（人工兜底）
* `GET  /api/v1/admin/dashboard` — 数据看板

### WebSocket

* `WS   /ws/merchant` — 商家端实时推送（新单/变更）

---

## 缓存与性能

* `/menu` **内存缓存**（TTL 3–5 min），库存/售罄调整后主动刷新。
* ORM 预加载（`selectinload/joinedload`），严禁 N+1 查询。
* PgBouncer 事务级连接池，减少握手与连接成本。

---

## 安全与鉴权

* **JWT**：用户与管理员分角色；WS 连接需携带 JWT。
* **幂等**：创建类接口必须带 `Idempotency-Key`，服务端记录 24h 窗口。
* **审计**：库存变更/功能开关/退款/手动匹配等写入 `audit_logs`。
* **WAF**：雷池作为唯一公网入口，开启限流与安全头。

---

## 可观测性

* **/metrics**（可选）导出 Prometheus 指标：

  * 订单创建/支付成功 QPS、匹配成功率、WS 在线数、打印失败率、缓存命中率
* **黑盒监控**：家→云 ping（CronJob）输出 RTT/丢包指标；Grafana 告警：连续5分钟均值>150ms 或丢包>2%。
* **日志**：结构化 JSON，PII 脱敏（手机号/交易号仅末4位）。

---

## 部署（K3s 混合云）

* 云：K3s **server** + 雷池 WAF + Postgres + PgBouncer + 后端 **主实例**（2 副本）
* 家：K3s **agent** + 后端 **热备实例**（1–2 副本，不对外暴露）
* Ingress 仅指向云端主实例；降级时由 K8s 调度与健康检查保障可用。

> 详见《后端＋混合云容灾一体化落地清单（可直接照做）V3.0+》

---

## 备份与容灾演练

* **数据库**：每日快照；季度恢复演练（含密钥/机密处理）。
* **降级演练**：断开家庭隧道，验证云端独活；恢复后家端保持热备。
* **对账任务**：每日 02:00 生成订单 vs. 支付流水差异报告。

---

## SLO 与容量规划

* `/menu` P95 ≤ 40ms（缓存命中 ≥95%）
* `/orders` P95 ≤ 200ms（家↔云 RTT ≤ 120ms）
* 支付回调成功率 ≥ 99.9%
* 触发扩容阈值：CPU>65%、常驻内存>80%、Postgres 活跃连接>70%、`/orders` P95>250ms

---

## 开发规范

* 提交信息：遵循 **Conventional Commits**（`feat:`, `fix:` 等）。
* 分支策略：`main`（稳定） / `develop`（集成） / `feature/*`（特性）。
* 代码风格：`black` + `ruff` + `isort`；`mypy`（可选）。
* PR 要求：必须附带 API 变更说明与测试用例。

---

## 项目规则（强制执行）

> 目标：**最小化开发**（如无必要不新增实体） · **最小占用开发**（基于最优解） · **全链路可回归**（每个 API/模块都配套完备测试）。

### 1) API 文档同步规则（doc/api.md 必写）

* **每实现/修改一个 API**，必须在 `doc/api.md` 中新增/更新记录；PR 若未包含对应文档改动 → **不予合并**。
* 变更类别：`新增` / `修改` / `弃用` / `删除`，需在条目中标注。
* 与 OpenAPI 保持一致：以 `doc/api.md` 为“人类可读”，以 `/docs` 为“机器可读”，两者字段/示例需一致。

#### `doc/api.md` 统一模板（复制使用）

````markdown
### [API 名称]
- **状态**：新增 | 修改 | 弃用 | 删除  （日期：YYYY-MM-DD）
- **路径/方法**：`[METHOD] /api/v1/...`
- **权限**：公开 | 用户JWT | Admin/Clerk
- **幂等**：是否需要 `Idempotency-Key`（是/否）
- **限流**：如：5 req/min/用户（WAF/应用层）
- **请求体**（示例 + 字段说明）：
```json
{
  "field": "value"
}
````

* **响应体**（示例 + 字段说明）：

```json
{
  "code": 0,
  "data": { ... },
  "trace_id": "..."
}
```

* **错误码**：列出业务错误（含场景、HTTP 状态）
* **副作用**：写库/发消息/打印任务/积分发放等
* **审计点**：是否写 `audit_logs`，记录哪些关键字段
* **观察指标**：需要打点的指标名（如 `order_create_total`）
* **测试清单**：

  * 正常流用例：
  * 异常流用例：参数缺失/权限/幂等重复/并发竞争…
  * 性能阈值：P95 ≤ X ms（样本 N）
* **变更历史**：

  * YYYY-MM-DD：说明


### 2) 最小化开发 / 最小占用开发（决策准则）
- **先复用，后新增**：能通过配置（`shop_settings` 特性开关）、通用字段（`meta_json`）或复用现有表表示的，不新增新表/新实体。
- **收敛字段**：同义字段合并，避免冗余口径（如价格统一在价格服务计算，不在多处重复保存）。
- **迁移审查**：每次数据库迁移需说明：动机、兼容性、回滚方案；禁止无必要的结构改动。
- **依赖最少**：若非必要，不引入新中间件/服务；能在现有 Postgres/内存缓存内解决的，不额外上分布式组件。

### 3) 测试规则（API/模块粒度）
- **每个 API 完成即写测试**：包含**正常流**、**异常流**、**边界&并发**、**幂等**、**权限**、**性能阈值**。
- **每个模块完成做模块回归**：订单、支付回调、匹配、打印、会员、预约、看板分别具备模块级集成测试。
- **覆盖率目标**：服务层（核心业务）覆盖率 ≥ **70%**；支付回调、匹配、打印队列、积分发券逻辑必须有用例。
- **数据构造**：使用工厂/fixtures；测试数据独立、可复放；对外依赖（支付/打印）使用 mock。
- **CI 要求**：`make lint && make test` 必过；关键路径新增需附压测结果（简单 wrk/hey 指标即可）。

### 4) 提交流程（拉通“规则落地”）
1. 立项/变更 → 写 `doc/api.md` 条目（草案）。
2. 开发 → 同步更新 OpenAPI 注释。
3. 单元/集成测试补齐（含幂等/并发/权限）。
4. PR：必须包含 `doc/api.md` 变更、测试用例、迁移脚本（若有）、回滚说明。
5. Reviewer 检查：规则对齐/文档一致性/测试完整性/性能阈值。
6. 合并后：在变更日志（CHANGELOG）登记用户可见影响。

---

## 目录结构
```

app/
api/            # 路由层（只做取参和返回）
core/           # 配置/日志/异常/依赖
models/         # ORM 模型（SQLAlchemy 2.0 async）
schemas/        # Pydantic 模型
services/       # 业务服务层（订单/支付/会员/打印/匹配）
workers/        # 后台任务（打印/对账/预约提醒）
ws/             # WebSocket 管理与Redis PubSub
utils/          # 距离/幂等/分页/加密/缓存
migrations/       # Alembic 迁移
charts/           # Helm/K8s 清单（可选）
scripts/          # 工具脚本（对账、备份、巡检）
infra/            # Dockerfile/compose，K3s 部署示例
tests/            # 单元/集成测试

```

---

```

app/
api/            # 路由层（只做取参和返回）
core/           # 配置/日志/异常/依赖
models/         # ORM 模型（SQLAlchemy 2.0 async）
schemas/        # Pydantic 模型
services/       # 业务服务层（订单/支付/会员/打印/匹配）
workers/        # 后台任务（打印/对账/预约提醒）
ws/             # WebSocket 管理与Redis PubSub
utils/          # 距离/幂等/分页/加密/缓存
migrations/       # Alembic 迁移
charts/           # Helm/K8s 清单（可选）
scripts/          # 工具脚本（对账、备份、巡检）
infra/            # Dockerfile/compose，K3s 部署示例
tests/            # 单元/集成测试

```

---

## 路线图
- ✅ V3.0：主流程与混合云容灾
- 🔜 V3.1：退款全链路、更多报表、降级体验提示（客户端）
- 🔭 V3.2：订单叫号屏、会员等级、A/B 实验与推荐

---

## 许可证
本项目默认 **私有**；如需开源请替换为合适的许可证（例如 MIT / Apache-2.0）。
