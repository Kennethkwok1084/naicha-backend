

## 关键确认（可行 👍）

* 目标与范围对齐：**建模 → 异步 ORM → Alembic 首迁移 → 初始化数据 → 测试验证**，流程完整。
* 技术选型匹配：`asyncpg + SQLAlchemy 2.0 async + Alembic` 没问题。
* 本地连接串、.env.example、CI 三件套都在 TODO 里覆盖到了。

---

## 微调建议（让 M1 更稳，更少返工）

1. **数据库连接与 Alembic 引擎差异**

   * 业务代码用 **async engine**；**Alembic env.py** 里仍需同步引擎（或使用 AsyncEngine 的官方模式）。最简单办法：

     * 应用：`postgresql+asyncpg://…`
     * Alembic：在 `env.py` 中把 DSN 替换为 `postgresql+psycopg2://…`（或使用 SQLAlchemy 的 async migration 模式）。避免异步迁移踩坑。

2. **命名规范与一致性**

   * 给 Alembic 配置 **命名约定**（naming convention），避免不同平台生成的约束名不一致：
     例：`pk_%(table_name)s`、`ix_%(table_name)s_%(column_0_label)s`、`uq_%(table_name)s_%(column_0_name)s`、`ck_%(table_name)s_%(constraint_name)s`、`fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`。
     这样后续自动迁移冲突会少非常多。

3. **ENUM vs CHECK**

   * 建议用 **CHECK 约束** 代替原生 ENUM（你已经写在 TODO 里了）：迁移简单、跨环境一致，后续新增值也不需要额外 DDL。

4. **金额与精度**

   * SQL 用 `NUMERIC(10,2)`；ORM 里用 `sqlalchemy.Numeric(scale=2, asdecimal=True)`。
   * **服务层统一四舍五入**入口（现金口径统一），避免多点散落。M1 先把字段类型与约束定死即可。

5. **updated_at 自动维护**

   * 两种做法选其一：

     * ORM 层：`Column(..., server_default=func.now(), onupdate=func.now())`（推荐，简单直接）。
     * DB 触发器：更严谨，但 M1 可先不做，避免迁移复杂度。

6. **外键删除策略**

   * 你列的几个表建议明确：

     * `order_items.order_id` → `ON DELETE CASCADE`
     * `product_categories.*`、`product_spec_mappings.*` → `ON DELETE CASCADE`
     * `payment_records.matched_order_id` → `ON DELETE SET NULL`
     * `coupons.used_in_order_id` → `ON DELETE SET NULL`
   * 这样历史数据可追溯且不会误删流水。

7. **初始化数据放哪儿？**

   * **推荐**：把**最小运行必需**的数据（`shop_profile(id=1)`、关键 `shop_settings`）写进首迁移的 `upgrade()`；
   * 而**易变数据（管理员默认账号）**放在 `scripts/seed_dev.py`，避免把密码哈希硬编码进迁移历史。
   * 如果你坚持迁移内插管理员，确保用**环境变量**注入哈希，或明确标注“开发专用，生产禁用”。

8. **索引一次到位**

   * 在首迁移就建好这些：

     * `orders(status, created_at DESC)`、`orders(user_id, created_at DESC)`、`orders(is_scheduled, scheduled_at) WHERE is_scheduled = TRUE`
     * `payment_records(paid_at DESC, amount)`、`payment_records(record_type, channel)`、`payment_records(matched_order_id)`
     * `coupons(user_id, status)`、`print_jobs(status, next_try_at)`、`want_events(product_id, created_at DESC)`
   * 能显著减少后续“慢 SQL”惊喜。

9. **测试数据库安全**

   * 尽量用**独立库**（如 `naicha_test`）或测试 schema，避免污染本地 dev 数据；
   * `pytest-asyncio` + `alembic upgrade head` 在 `session` 级 fixture；每条测试在**事务回滚**或 **DB teardown**，保证可重复。

10. **.env 与 secrets**

* `.env.example` 中放**占位**而不是真密钥，实际密钥通过 `.env` 或 CI Secret 注入；
* 你这次给的连接串（`postgresql/Onjuju1084`）**仅用于本地**，确认不会入仓库历史。

---

## 初始化数据建议清单（可用于首迁移 or 种子脚本）

* **shop_profile**（id=1）：

  * `is_open=true`、`open_hours_json=[]`（先空）、`delivery_radius_m=1500`、`timezone='Asia/Shanghai'`
* **shop_settings**（最小集）：

  * `MULTI_CATEGORY_ENABLED=false`
  * `RESERVATION_ENABLED=false`
  * `WANT_ENABLED=true`
  * `SOLDOUT_STYLE='hide'`  （V1.1 可置灰，但后端先输出 `inventory_status` 字段）
  * `RESERVATION_REMINDER_MINUTES=15`
  * `STATIC_MATCH_TIME_WINDOW_MIN=5`
  * `DELIVERY_RADIUS_M=1500`
  * `PRINT_RETRY_MAX=5`
* **admins**（开发专用，可放 seed 脚本）：

  * `username='admin'`、`password_hash=bcrypt('admin123' 或环境提供)`、`role='admin'`

> 注：生产环境建议通过运维脚本创建管理员，避免迁移里出现固定账号。

---

## M1 验收清单（Go/No-Go）

**建模与迁移**

* [ ] `alembic upgrade head` 成功；`downgrade base` 成功
* [ ] 关键表/约束/索引存在且与文档一致
* [ ] `created_at/updated_at` 正常；状态列 CHECK 生效
* [ ] 外键 `ON DELETE` 行为符合预期（做一条级联删除用例）

**初始化数据**

* [ ] `shop_profile(id=1)` 成功插入
* [ ] `shop_settings` 关键键存在且值正确
* [ ] 管理员初始化策略明确（迁移 or 种子），生产禁用默认弱口令

**ORM & 会话**

* [ ] `AsyncSession` 正常；简单 CRUD 用例跑通
* [ ] Alembic 与应用的引擎配置清晰（async vs sync）

**测试**

* [ ] `tests/db/` 中的迁移回滚测试通过
* [ ] 建表后的最小 CRUD/外键/索引命中用例通过
* [ ] `make fmt && make lint && make test` 全绿

---

## 小提示（加速你 Day 3–5 的推进）

* 在 `app/db/base.py` 里集中 **import 所有模型** 到 `Base.metadata`，确保 Alembic autogenerate 能发现它们。
* 金额字段的 **Pydantic Schema** 统一用 `condecimal(max_digits=10, decimal_places=2)`，避免上层误传。
* 给 `orders.order_number` 写一个**唯一索引 + 生成器**（服务层），M1 先不写触发器，M3 再评估是否要 DB 侧生成。

---

总体来看，**你的 M1 计划就按这个执行就行**，上面这些收口会帮你后面少踩很多坑。

