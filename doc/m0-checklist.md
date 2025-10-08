# M0 任务清单

- [x] 项目骨架：`app/`（api/core/models/schemas/services/workers/utils/ws）、`migrations/`、`tests/`、`infra/`、`scripts/` 搭建完成。
- [x] 配置系统：基于 `.env` → `app/core/settings.py` 管理 JWT、数据库、代理、Feature Flags 默认值。
- [x] 基础中间件：结构化日志、统一异常、CORS 白名单、SlowAPI 限流占位路由。
- [x] 健康检查：提供 `/healthz`、`/metrics`（支持 `PROMETHEUS_ENABLED` 开关）。
- [x] 容灾基线：记录主在云端的拓扑与 SLO（`/menu` P95 ≤ 40ms、`/orders` P95 ≤ 200ms、WS ≤ 5s）于 `doc/m0-baseline.md`。
- [x] 文档与规范：完成 `doc/api.md` 模板与 Conventional Commits 指南。
- [x] 验证：`make test`（pytest）通过，确保骨架可运行。
