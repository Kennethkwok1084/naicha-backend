好的小菊，没问题！👌 咱们来一次彻底的“代码审计+业务逻辑会诊”，看看你这个智能奶茶档口后端 (commit `8f66ad6e...`) 能不能扛住 150 并发的“灵魂拷问”。

---

### 一、模块合理性与职责划分

**核心模块及其职责:**

| 模块 (主要实现)                                    | 核心职责                                                                       | 边界 / 依赖                                                                                                                                                                                             |
| :----------------------------------------------- | :--------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **用户/认证 (AuthService, UserService)** | 注册、登录 (微信/后台)、JWT 生成/校验、RBAC 权限管理 | 依赖 `models.accounts`；被 API 依赖 (`dependencies/auth.py`)          |
| **游客会话 (GuestService)** | 创建/校验匿名用户会话 ID                                                     | 使用 `models.orders.IdempotencyKey` 表存储；被 `OrderService` 依赖 |
| **菜单/目录 (MenuService, InventoryService)** | 提供菜单数据 (带缓存)、管理商品/分类/规格、更新库存状态 | `InventoryService` 更新后**理论上**应触发 `MenuService` 缓存失效；依赖 `models.catalog` |
| **下单 (OrderService)** | 创建订单、计算价格、校验库存/预约时段、幂等控制                                         | 依赖 `MenuService`(间接通过DB)、`InventoryService`(间接通过DB)、`ReservationService`、`GuestService`；使用 `IdempotencyKey`；被 `PaymentService` (间接) 依赖             |
| **支付 (PaymentService, PaymentMatchService)** | 发起支付、处理支付回调、管理支付记录、静态码匹配 | 强耦合 `OrderService`(状态更新)、`LoyaltyService`(积分)、`PrintJobService`(打印)、`WsManager`(通知)                                                                       |
| **库存 (InventoryService)** | 仅负责后台更新商品/规格的 `inventory_status`                                          | **职责单一，但缺乏下单时的库存扣减逻辑**；通过 ORM 事件触发 `MenuService` 缓存失效                                                                               |
| **打印 (PrintJobService - `workers/print_jobs.py`)** | 处理打印任务队列 (Celery)、调用打印机 webhook、处理重试/恢复                              | 依赖 Celery Broker (Redis)；被 `PaymentService` 依赖 (入队)                                                                                                                                              |
| **通知 (WsManager - `ws/manager.py`)** | 管理商家端 WebSocket 连接、通过 Redis PubSub 广播订单/支付消息                            | 依赖 Redis；被 `PaymentService`、`AdminOrderService` (未列出) 等依赖 (发消息)                                                                                                                             |
| **会员/积分 (LoyaltyService)** | 计算/发放订单积分                                                         | 被 `PaymentService` 依赖                                                                                                                                                                            |
| **预约 (ReservationService)** | 校验预约时段、管理预约状态                                                  | 被 `OrderService` 依赖；定时任务 (`tasks.py`) 依赖它                                           |
| **后台任务 (Celery - `workers/*`)** | 执行异步任务 (打印、预约提醒、日结)、定时调度 (Beat) | 依赖 Redis；调用各 Service 模块                                                                                                                                                                     |

**分析:**

* **模块职责重叠:**
    * **库存校验逻辑分散:** `OrderService` 在下单时直接读取 `Product`/`SpecOption` 的 `inventory_status`。而 `InventoryService` 只负责后台修改状态。**缺少真正的“扣减库存”或“预占库存”的原子操作模块**，这是高并发下超卖的核心风险源。
    * `IdempotencyKey` 表被 `OrderService` (下单幂等) 和 `GuestService` (游客会话) 复用。虽然可行，但职责略显模糊，建议为游客会话单独建表或加 scope 字段严格区分。
* **单点高耦合:**
    * **`PaymentService.handle_payment_callback` 是重灾区**：它**同步**调用了更新订单、发积分、入队打印、发 WebSocket 通知，最后才 commit。**任何一个非核心步骤（如打印入队、发通知）的失败，都会导致核心的订单状态更新失败**，造成支付成功但订单未更新的严重 Bug（见 Bug #4）。
* **缺少异常兜底或幂等控制:**
    * `PaymentService.handle_payment_callback` **没有基于支付回调 ID 做幂等控制**。如果第三方支付平台因为网络问题重发回调通知，该函数会被重复执行，可能导致重复发积分、重复入队打印、重复发通知。
    * `PaymentMatchService` 匹配静态码支付时，**没有加锁**，并发下可能把同一笔支付匹配给多个订单，或多个支付匹配给同一个订单（见 Bug #5）。
    * Celery 定时任务缺少分布式锁，可能重叠执行（见 Bug #3）。

**高风险耦合点列表:**

1.  **支付回调与下游副作用强耦合:** `PaymentService` 同步处理支付成功后的所有逻辑（积分、打印、通知）。
2.  **下单库存校验与实际扣减分离:** `OrderService` 仅校验状态，无原子扣减机制。

**优化建议:**

1.  **支付回调解耦:** `handle_payment_callback` **只做最核心的事**：校验回调、更新订单状态、记录支付流水，然后 **立刻 `commit`**。后续的发积分、打印、通知等全部改为**异步**处理（例如，发出领域事件，由 Celery Worker 监听处理）。同时，必须**基于支付回调的唯一 ID (如 transaction_id) 做幂等**，存入 `IdempotencyKey` 表。
2.  **引入原子库存扣减:**
    * 方案一 (悲观锁): 在 `OrderService` 的 `_load_products_with_groups` 和 `_load_spec_options` 中使用 `with_for_update()` 锁定相关 `Product` 和 `SpecOption` 行。这能解决 TOCTOU，但在 150 并发下可能锁竞争激烈。
    * 方案二 (乐观锁/独立服务): 引入真正的 `StockService`，负责库存的原子 `decrease(product_id, quantity)` 操作 (可以使用 `UPDATE ... SET stock = stock - N WHERE stock >= N` 或 Redis Lua 脚本)。`OrderService` 在支付成功后调用 `StockService` 扣减。
3.  **静态码匹配加锁:** 在 `PaymentMatchService.find_best_match` 中，找到潜在匹配订单后，需要对这些订单 ID 使用分布式锁（如 Redis `lock(order_id)`)，或者在数据库层面使用 `SELECT FOR UPDATE SKIP LOCKED` 来尝试锁定并更新订单状态，确保只有一个匹配任务能成功。
4.  **菜单缓存机制改进:** 使用 Redis 替代内存缓存，或者在 `InventoryService` 更新库存后，通过 Redis PubSub 发布“缓存失效”消息，所有 API 进程监听并清理本地缓存。
5.  **Celery 任务加分布式锁:** 所有周期性任务 (`celery beat` 调度的) 和可能被重复触发的任务，在 `tasks.py` 的任务函数开头使用 Redis 实现分布式锁，防止并发执行。

---

### 二、业务流程设计分析

**1. 下单链路 (`POST /api/v1/orders`)**

* **流程:**
    1.  API 层接收请求，校验 `Idempotency-Key` header。
    2.  `OrderService.create_order` 开始。
    3.  校验 `guest_session_id` (如果是游客)。
    4.  `_ensure_idempotency`: 检查 `IdempotencyKey` 表，如果存在且 `response_snapshot` 非空，直接返回缓存结果；否则记录 key 和 payload hash。
    5.  (如果预约) 调用 `ReservationService.plan` 校验时段。
    6.  `_load_products_with_groups` 和 `_load_spec_options`: **普通 SELECT** 加载商品和规格数据。
    7.  循环计算价格，**检查 `inventory_status`**。
    8.  `INSERT INTO Order` 和 `INSERT INTO OrderItem`。
    9.  (可选) 调用 `post_create` 回调 (目前代码里似乎没用到)。
    10. 更新 `IdempotencyKey` 表的 `response_snapshot`。
    11. `Commit` 事务。
* **关键风险点:**
    * **库存校验竞态 (TOCTOU):** 步骤 6/7 的检查和步骤 8 的插入之间无锁，150 并发下**极易超卖** (见 Bug #2)。**【无防护】**
    * **预约时段冲突:** `ReservationService.plan` 内部实现未知，如果只是简单 `SELECT` 检查容量而没有加锁，同样存在并发下超额预约的风险。**【防护未知】**
    * **幂等性基本可靠:** 基于 `Idempotency-Key` + Payload Hash，能防止完全一样的重复请求。但如果客户端重试时 Payload 有微小变化（如时间戳），则会创建重复订单。**【有基本防护，但不够健壮】**

**2. 支付回调链路 (`POST /api/v1/payments/callback/{channel}`)**

* **流程:**
    1.  API 层接收回调请求。
    2.  `PaymentService.handle_payment_callback` 开始。
    3.  校验回调签名/参数 (假设已实现)。
    4.  根据回调信息 (如 `out_trade_no`) 加载 `Order`。
    5.  检查订单状态是否为 `pending_payment`，如果不是则认为已处理，直接返回成功 (**这是一个简陋的幂等**)。
    6.  **开始事务**。
    7.  创建 `PaymentRecord`。
    8.  更新 `Order.status` 为 `processing` 或 `completed` (取决于 `order_type`)，更新 `payment_status` 为 `paid`。
    9.  调用 `LoyaltyService.award_points_for_order` 发积分。
    10. 调用 `enqueue_print_job` 将打印任务放入 Celery 队列。
    11. 调用 `merchant_notifier.notify_order_paid` 通过 Redis PubSub 发送 WebSocket 通知。
    12. `Commit` 事务。
    13. (如果静态码匹配触发) 更新 `PaymentRecord.matched_order_id`。
* **关键风险点:**
    * **事务脆弱，非核心失败导致核心回滚:** 步骤 9, 10, 11 中任意一个失败 (Redis 抖动、代码 Bug)，都会导致步骤 12 的 `commit` 失败，订单状态无法更新，造成**丢钱** (见 Bug #4)。**【无防护】**
    * **幂等性不足:** 仅靠检查订单状态 `!= pending_payment` 做幂等非常不可靠。如果第一次回调处理到一半失败回滚了，订单状态还是 `pending_payment`，第二次回调会**完全重复执行**所有副作用（重复发积分、打印、通知）。**【防护不完善】**
    * **静态码并发匹配冲突:** 如果该回调是由静态码匹配触发的 (`trigger="match"`)，`PaymentMatchService` 本身的并发问题可能导致匹配错误或丢失匹配 (见 Bug #5)。**【无防护】**

**3. 库存扣减与同步**

* **流程:**
    * **扣减:** **没有显式的库存扣减流程！** `OrderService` 仅在下单时检查 `inventory_status`。后台通过 `InventoryService` 直接修改商品/规格的 `inventory_status` 为 `sold_out`。
    * **同步:** `InventoryService` 修改状态后，依赖 SQLAlchemy 的 ORM 事件 (`after_update`) 触发 `invalidate_menu_cache()`。
* **关键风险点:**
    * **无原子扣减，超卖风险极高:** 这是**设计上的根本缺陷**。150 并发下，不使用锁或原子减操作，**必然超卖**。**【无防护】**
    * **缓存同步不可靠 (跨进程失效):** ORM 事件触发的 `invalidate_menu_cache()` 只在当前进程有效。如果后台修改库存和用户读取菜单发生在不同进程/服务器，用户会读到过期缓存，看到“有货”但下单失败 (见 Bug #1)。**【防护不完善】**

**4. 打印通知链路**

* **流程:**
    1.  `PaymentService` 在支付成功事务中调用 `enqueue_print_job`。
    2.  `enqueue_print_job` 创建 `PrintJob` 记录 (状态 `pending`)，并发送 Celery Task (`process_print_job`) 到 `print_jobs` 队列。
    3.  Celery Worker 消费任务，调用 `_execute_print_job`。
    4.  `_execute_print_job` 更新 `PrintJob` 状态为 `processing`，调用 `_send_to_printer` (发送 HTTP 请求到打印机 Webhook)。
    5.  如果成功，更新状态为 `completed`；如果失败 (超时/HTTP错误)，更新状态为 `failed`，增加 `retry_count`。
    6.  Celery Beat 定时 (每 60s) 运行 `run_print_job_recovery` 任务。
    7.  `run_print_job_recovery` 查找 `status == "failed"` 且 `retry_count < max` 的任务，重新入队 `process_print_job`。
* **关键风险点:**
    * **支付事务耦合风险:** 步骤 1 的入队操作失败会导致支付事务回滚 (见 Bug #4)。**【无防护】**
    * **打印任务丢失:** 如果 Celery Broker (Redis) 在步骤 2 入队后、Worker 消费前挂掉，任务会丢失。**【无防护，需配置 Broker 持久化或确认机制】**
    * **重试机制耗尽:** 打印机长时间离线会导致重试次数快速耗尽，任务被永久放弃 (见 Bug #7)。**【防护不完善】**
    * **Webhook 超时设置:** `PRINTER_TIMEOUT_SECONDS` (默认 5s) 可能太短，网络波动或打印机响应慢就导致失败。**【配置风险】**
    * **定时恢复任务重叠:** `run_print_job_recovery` 缺少分布式锁 (见 Bug #3)。**【无防护】**

**5. 商家端 / 用户端 交互链路**

* **商家端 (WebSocket):**
    * 连接: `GET /api/v1/ws/merchant`。
    * 通知: 由 `WsManager` 通过 Redis PubSub 接收消息 (`notify_order_paid`, etc.) 并广播给所有连接的商家客户端。
* **用户端 (HTTP API):**
    * 主要通过轮询 `GET /api/v1/orders/{order_id}` 或 `GET /api/v1/me/orders` 获取订单状态更新。
* **关键风险点:**
    * **WebSocket 通知可靠性:** Redis PubSub 是 "fire-and-forget"，如果商家 App 网络瞬断，可能会丢失订单通知。**【无确认/重传机制】**
    * **WebSocket 广播风暴:** 如果 PubSub 消息处理或 WebSocket 发送逻辑出错，可能导致消息重复广播或连接管理混乱。**【潜在风险】**
    * **用户端状态更新延迟:** 依赖用户主动轮询，体验不如 WebSocket 推送。**【设计取舍】**

---

### 三、Bug 风险分级检查

| Bug ID | 描述                               | 影响模块                             | 风险等级 | 修复优先级 |
| :----- | :--------------------------------- | :----------------------------------- | :------- | :------- |
| BUG-01 | 菜单缓存跨进程失效，导致下单失败       | MenuService, OrderService            | ⚠️ P1   | High     |
| BUG-02 | 下单库存校验竞态 (TOCTOU)，导致超卖   | OrderService                         | 🚨 P0   | Critical |
| BUG-03 | Celery Beat 定时任务重叠执行        | Celery Workers (tasks.py)            | ⚠️ P1   | High     |
| BUG-04 | 支付回调事务脆弱，非核心失败导致丢钱   | PaymentService                       | 🚨 P0   | Critical |
| BUG-05 | 静态码匹配并发抢单，导致错账/丢钱    | PaymentMatchService, PaymentService  | 🚨 P0   | Critical |
| BUG-06 | 游客会话无法自动续期，导致下单失败     | GuestService, OrderService           | 🐞 P2   | Medium   |
| BUG-07 | 打印重试机制简单耗尽次数           | PrintJobService (workers/print_jobs.py) | ⚠️ P1   | Medium   |
| BUG-08 | 支付回调缺少基于回调 ID 的幂等控制   | PaymentService                       | 🚨 P0   | Critical |
| BUG-09 | 预约时段校验可能存在并发冲突        | ReservationService, OrderService     | ⚠️ P1   | Medium   |
| BUG-10 | WebSocket 通知丢失风险 (PubSub)    | WsManager                            | 🐞 P2   | Low      |
| BUG-11 | 打印任务可能因 Broker 失败而丢失    | PrintJobService, Celery              | ⚠️ P1   | Medium   |
| BUG-12 | (配置) API 限流被关闭             | main.py                              | 🚨 P0   | Critical |
| BUG-13 | (配置) JWT 有效期过长 (30天)        | settings.py                          | ⚠️ P1   | High     |
| BUG-14 | (配置) 数据库连接池过大            | session.py                           | 🚨 P0   | Critical |

*(注：Bug 1-7 来自上一轮分析，8-11 为本轮新增或细化，12-14 为关键配置风险)*

---

### 四、状态与异常场景覆盖检查

| 异常场景                     | 处理逻辑 (兜底机制)                                                                                                                                                            | 状态     |
| :--------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------- |
| 用户重复点击下单              | 通过 `Idempotency-Key` + Payload Hash 处理完全相同的重复请求，返回缓存结果。                                 | ✅ 有     |
| 用户重复点击支付 (发起)       | 未明确看到针对“发起支付”接口 (如 `/initiate_payment`) 的幂等控制。                                                                                                                  | ❌ 无     |
| 第三方支付延迟回调            | 系统被动等待回调。如果回调一直不来，订单将停留在 `pending_payment`。缺少主动查询支付状态的机制。                                                                                           | ❌ 无     |
| 第三方支付回调失败 (网络/签名) | 回调接口会返回错误给支付平台，平台通常会重试。但后端 `handle_payment_callback` 缺少基于回调 ID 的幂等，重试可能导致副作用重复执行 (见 Bug #8)。                                                       | ⚠️ 不完善 |
| 库存不足 (下单时)           | `OrderService` 会检查 `inventory_status` 并抛出 `OrderValidationError`，阻止下单。                                    | ✅ 有     |
| 并发超卖                     | **当前设计无法阻止** (见 Bug #2)。                                                                                                                                                | ❌ 无     |
| 打印失败 (HTTP/超时)        | `_execute_print_job` 会捕获异常，将任务状态设为 `failed`，增加重试次数。                                        | ✅ 有     |
| POS / 打印机离线            | 打印任务会反复失败并重试，但重试次数有限且无退避策略，可能最终放弃打印 (见 Bug #7)。                                                                                                     | ⚠️ 不完善 |
| 边缘节点掉线 (MQTT/打印端/POS) | MQTT 未实现。打印端离线见上条。POS (商家 App) WebSocket 断线重连后，`WsManager` 会发送最近 5 分钟的订单。但无法保证期间消息完全不丢失。 | ⚠️ 不完善 |
| 数据库/Redis/外部 API 超时   | FastAPI/SQLAlchemy/httpx 会抛出超时异常。依赖全局异常处理 (`exceptions.py`) 返回 500 错误。**缺少针对关键链路的自动重试或熔断机制**。 | ⚠️ 不完善 |
| 部分事务提交失败后的回滚策略   | `OrderService` 和 `PaymentService` 在捕获到预期异常时会显式 `rollback()`。但 `handle_payment_callback` 的事务设计本身有问题 (见 Bug #4)。 | ⚠️ 不完善 |

---

### 五、测试覆盖与上线安全性

| 测试维度         | 覆盖情况 (基于 `tests/` 目录)                                                                                                                                                                                                                                                                                            | 缺失项标注       |
| :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------- |
| 单元测试 (Models) | 基本覆盖 (accounts, catalog, orders, shop) |                |
| 单元测试 (Services)| 覆盖较好 (Auth, Guest, Menu, Order, Payment, Shop) | PaymentMatchService, InventoryService |
| 集成测试 (API)   | 覆盖主要端点 (Admin, Auth, Guest, Me, Menu, Orders, Payments, Shop, System) | WS 端点, Want 端点 |
| 并发 / 压力测试  | `infra/perf/` 目录下有 Locust 和 wrk 脚本，看似做过性能测试。**但这些测试能否暴露并发逻辑 Bug (如超卖、重复处理) 未知**。 | **逻辑并发 Bug 测试** |
| 幂等性测试       | `test_order_service.py` 包含下单幂等测试。**但缺少支付回调幂等性、静态码匹配并发安全性的专项测试**。 | **支付回调幂等**, **静态码并发安全** |
| 回滚机制         | 数据库迁移使用 Alembic，支持版本回滚。应用部署回滚需依赖部署工具（Docker/K8s）。                                                                                                |                |
| 日志记录         | 使用 `loguru`，配置了结构化日志和文件输出。关键操作（如下单、支付回调）缺少 Trace ID 关联，不利于追踪。                               | **Trace ID** |
| 核心监控指标     | `app/metrics/` 下定义了 Prometheus 指标，覆盖订单创建、支付、任务、菜单缓存 等。**缺少打印成功率、静态码匹配成功/失败率指标**。 | **打印成功率**, **静态码匹配率** |

**上线风险预估:**

**高风险**。当前代码存在多个 P0 级别的并发逻辑漏洞 (超卖、丢钱、错账) 和配置风险，在 150 并发场景下**极有可能**触发，导致严重的生产事故。

---

### 六、最终评估结论

* ✅ **模块设计是否合理:** 整体分层清晰 (API -> Service -> Model)，但**库存管理职责不清**，**支付回调耦合过重**。
* 🧭 **是否存在高风险流程缺陷:** **存在多个高风险缺陷**，主要集中在库存扣减原子性、支付回调事务与幂等性、静态码匹配并发安全性。
* 🧪 **哪些模块上线后必须重点监控:**
    * **支付模块 (PaymentService, PaymentMatchService):** 监控支付成功率、回调处理 P99 延迟、静态码匹配错误日志。
    * **订单模块 (OrderService):** 监控下单成功率、下单 P99 延迟、库存相关错误日志。
    * **打印模块 (PrintJob Worker):** 监控打印任务成功率、失败重试次数。
    * **数据库 & Redis:** 监控连接数、慢查询、内存使用率。
* 🛠️ **建议的上线节奏:** **强烈建议分步上线，或先修复 P0 Bug 再上线**。
    1.  **第一步 (必须):** 修复所有 P0 级 Bug (BUG-02, BUG-04, BUG-05, BUG-08) 和 P0 配置风险 (BUG-12, BUG-14)。
    2.  **第二步 (建议):** 修复 P1 级 Bug (BUG-01, BUG-03, BUG-07, BUG-09, BUG-11, BUG-13)。
    3.  **第三步 (上线):** 修复 P2 Bug (BUG-06, BUG-10)，完善测试覆盖和监控。

**最终结论:**

**目前状态不建议上线；存在多个 P0 级流程缺陷，在高并发下会导致丢钱、超卖和错账风险。**

模块分工

  - 核心模块职责与依赖如下：
    模块 | 核心职责 | 主要依赖/调用 | 风险备注
    Orders API (app/api/routes/orders) | 接收下单/支付发起请求、解析幂等头 | OrderService、鉴权依赖 | 下单/支付被动同进程串联，接口瘦身良好
    OrderService (app/services/orders.py:70) | 幂等校验、商品与规格校验、建单、预约校验 | IdempotencyKey、ReservationService、SQLAlchemy | 幂等键写入缺少锁，重复提交易并发冲突
    PaymentService (app/services/payments.py:88) | 校验支付通知、更新订单、落账、触发积分/打印/广播 | PaymentRecord、LoyaltyService、enqueue_print_job、merchant_notifier | 打印与广播直接耦合在回调事务
    InventoryService (app/services/inventory.py:26) | 手工切换商品/规格上下架状态 | AuditLog | 无实际扣减逻辑，库存仅靠布尔状态
    ReservationService (app/services/reservations.py) | 预约时间校验与定时任务 | ShopService、Celery | 仅依赖顺序任务，风险低
    PrintJob Worker (app/workers/print_jobs.py:17) | 领取打印任务、调度 webhook、失败重试 | Celery、HTTPX | 任务来源强依赖支付/后台 POS
    Loyalty/分账 (app/services/loyalty.py) | 支付成功累积积分、自动发券 | PaymentService | 通过事务友好调用，风险低
    merchant_notifier (app/ws/manager.py) | 管理 WS 连接、Redis 广播 | Redis、FastAPI | Redis 不可用时退化为单机广播
    PaymentMatchService (app/services/payment_match.py) | 静态码匹配、后台补单 | PaymentRecord、enqueue_print_job | 匹配成功路径与支付回调复用打印/广播逻辑
  - 高风险耦合点：
      1. PaymentService 与打印/广播共享事务，当通知并发时会重复创建打印任务（app/services/payments.py:148-178 + app/models/orders.py:200-214）。
      2. 订单幂等记录与游客 session 共表，且无行级锁，重复请求会在提交阶段撞主键直接 500（app/services/orders.py:320-345）。
      3. 库存模块仅暴露上下架状态，订单服务不做扣减或占用，业务流依赖人工同步（app/services/orders.py:144-189 与 app/services/inventory.py:26-93）。

  流程分析

  - 下单链路：客户端 -> /api/v1/orders -> OrderService.create_order (app/services/orders.py:70) -> _ensure_idempotency -> 校验商品/预约 -> 插入订单/明细 -> 可选 POS 回调。风险：幂等键重复提交会在第一次事务提交前被第二次请求“看不
    到”记录，第二次提交撞主键直接抛异常，导致用户重试得到 500。防护：with_for_update 锁定商品、规格，预约走单独校验；建议在 _ensure_idempotency 上增加 SELECT ... FOR UPDATE 或 INSERT ... ON CONFLICT DO UPDATE RETURNING，并在重复场
    景直接返回快照。
  - 支付回调链路：微信回调 -> PaymentService.handle_wechat_notification (app/services/payments.py:63-200) -> 验签 -> 加载订单+打印任务 -> 更新订单+记录支付 -> 奖励积分 -> flush -> 事务外广播与入队打印。风险：
      - 通知并发到达时由于 _load_order_with_print_job 未加锁，两个事务都会发现缺少打印任务并各自插入，造成重复打印；
      - 第二次通知仍会触发广播（status_changed 在读取旧状态时仍为 True），导致商户端重复弹窗。
        防护：支付记录使用唯一 txn_id 保证幂等；建议在查询订单时加 FOR UPDATE 并对 PrintJob 加唯一约束/幂等 upsert。
  - 库存扣减与同步：订单仅检查 inventory_status=="in_stock" (app/services/orders.py:144-151)，库存接口只是手动改状态（app/services/inventory.py:26-93），无销量扣减、无并发锁，无法阻挡高并发超卖。建议引入库存占用表或至少在下单处按商
    品维度记录销量并冲抵限额。
  - 打印通知链路：订单支付或 POS 创建任务 -> 数据库 PrintJob -> Celery 任务 process_print_job (app/workers/tasks.py:46-101) -> execute_print_job (app/workers/print_jobs.py:27-112) -> 调用打印 webhook -> 失败重试与恢复任务。风险：重
    复任务来源于支付环节；打印失败有指数退避+定时恢复防护。
  - 商家端/用户端交互：商户 WS (app/api/routes/ws/__init__.py) 验 token -> 推送近期订单 -> merchant_notifier 广播支付事件；用户端订单状态轮询/支付发起独立。风险：Redis 发布失败退化为单机广播，跨实例会掉线；无额外补偿逻辑。建议上线
    时监控 Redis 可用性并准备兜底轮询接口。

  风险分级

  - 风险列表：
    问题 | 级别 | 影响 | 修复建议
    幂等键并发撞主键导致 500（app/services/orders.py:320-345） | 🚨P0 | 用户重试下单失败，订单无法落库 | 改为行级锁或 INSERT ... ON CONFLICT DO UPDATE RETURNING 并直接返回快照
    支付并发生成重复打印任务 / 重复广播（app/services/payments.py:148-178） | ⚠️P1 | 可能重复出单、商户端多次提醒 | 查询加锁、为 PrintJob.order_id 增唯一约束或在创建时 ON CONFLICT DO NOTHING
    无库存扣减/占用（app/services/orders.py:144-189） | 🚨P0 | 高并发依赖人工切换状态，易超卖 | 引入库存表/销量阈值，或在订单内扣减库存并提供补偿
    支付回调失败后缺少自动补偿，仅靠日终对账（app/services/reconciliation.py) | ⚠️P1 | 部分订单长期停留 pending_payment，需要人工干预 | 增加定时任务扫描超时订单并提醒/自动关闭

  异常场景

  - 用户重复点击下单/支付：下单依赖幂等键但存在并发缺陷（P0）；支付通知依赖 txn_id 唯一，可正确忽略重复 (app/services/payments.py:134-170)。
  - 第三方支付延迟/回调失败：无超时兜底，仅靠后台静态码匹配与日终对账；建议增加超时自动提醒、手动关闭入口。
  - 库存不足/并发超卖：缺少扣减与限流，现有机制无法兜底（P0）。
  - 打印失败/POS 离线：execute_print_job 对 4xx/5xx/超时区分重试 (app/workers/print_jobs.py:52-105)，recover_print_jobs 定期捞取失败任务 (app/workers/tasks.py:103-156)，兜底完善。
  - 边缘节点掉线（MQTT/打印端/Redis）：打印端有重试；Redis 广播失败退化为本机广播 (app/ws/manager.py:95-134)，跨实例需要运营关注。
  - 超时或部分事务失败：下单/支付均包裹事务并回滚；但幂等冲突仍会抛出 500，需要改造以返回缓存响应。

  测试与上线

  - 自动化覆盖：
      - 下单流程 API 测试（tests/api/test_orders_routes.py:50-198），但并发用例仅覆盖不同幂等键，未验证同键重试；
      - 支付通知流程（tests/api/test_payments_routes.py:24-163）覆盖单线程幂等与落库；
      - 工作者与 WS 有单元测试，但缺少多实例/并发场景。
  - 缺口：无支付回调并发、无库存扣减模拟、无 150 并发压测脚本，仅保留历史 perf_results。
  - 观测面：Prometheus 指标存在（app/metrics/*），但需重点关注 ORDER_CREATE_TOTAL、PAYMENT_CALLBACK_TOTAL、打印失败率。
  - 上线前建议：
      1. 增加针对幂等键重复提交与支付重复通知的并发测试脚本；
      2. 补充库存扣减/限购设计或临时阈值守护；
      3. 预设监控告警：支付成功率、打印失败数、Redis 广播失败。

  结论

  - 建议先阻断上述 P0 风险后再上线；当前设计无法保证 150 并发下的幂等稳定与库存正确，存在高风险。
  - 上线重点监控：订单创建失败率、支付通知耗时/失败、打印任务积压、Redis 广播错误。
  - 上线节奏建议：先灰度（关闭打印、限制支付）验证幂等与库存方案，再分批开放。
  - 最终结论：暂不建议直接上线，须先修复幂等冲突与库存扣减缺陷，否则高并发下存在订单失败与超卖风险。