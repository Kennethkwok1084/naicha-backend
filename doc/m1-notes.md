# M1 数据层说明

## 数据库连接
- 默认开发连接：`postgresql+asyncpg://postgres:Onjuju1084@localhost:5432/naicha`
- 测试固定使用库：`naicha_test`（测试脚本会自动创建/复用，并在完成后回滚到 `base`）
- Alembic 迁移使用同步 DSN，`env.py` 会自动把 `+asyncpg` 替换为 `+psycopg2`

## 迁移与初始化
- `alembic upgrade head` 会创建所有业务表、索引与 CHECK 约束
- 首次迁移写入 `shop_profile(id=1)` 与核心 `shop_settings`
- `alembic downgrade base` 可回滚验证（测试用例在执行中覆盖）

## 开发环境管理员
- 迁移不包含默认管理员，避免弱口令进入历史
- 开发环境可运行 `python scripts/seed_dev.py`，需提供 `NAICHA_DEV_ADMIN_HASH`（bcrypt 哈希）和可选 `NAICHA_DEV_ADMIN_USERNAME`
- 生产环境必须通过运维流程创建管理员账号

## 模型与字段约束
- 金额统一使用 `NUMERIC(10,2)`，服务层负责四舍五入
- 状态字段均有 `CHECK` 约束（如 `orders.status`、`payment_records.match_status`）
- 核心索引在首迁移一次到位：`orders`、`payment_records`、`print_jobs`、`coupons`、`want_events` 等
- `idempotency_keys` 包含 `request_hash`、`response_snapshot`、`expire_at`；`audit_logs` 预留 `prev_hash/curr_hash`

## 测试说明
- `tests/db/test_migrations.py` 流程：
  1. 连接 `naicha_test`，如不存在自动尝试创建
  2. 强制回滚至 `base`，执行 `upgrade head`
  3. 断言 `shop_profile` 与关键配置写入
  4. 再回滚至 `base`，保持数据库干净
- 如无法连接数据库会直接失败并提示启动本地 PostgreSQL

## 注意事项
- `app/db/base.py` 显式 import 全部模型，保障 Alembic autogenerate 可用
- `.env.example` 仅存放占位信息，实际机密请放在 `.env` 或 CI Secrets
- 修改模型后务必执行 `make fmt && make lint && make test` 验证

