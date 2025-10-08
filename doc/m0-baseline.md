# M0 环境与容灾基线

## 拓扑概览
- **应用层**：FastAPI (`app/`) 运行在 Uvicorn 上，默认通过 `make dev` 或 `docker compose up -d --build` 启动。
- **数据层**：PostgreSQL 主库 + PgBouncer 连接池；默认连接串 `DATABASE_URL=postgresql+asyncpg://user:pass@pgbouncer:6432/naicha`。
- **缓存策略**：后续将以内存缓存热点接口（如 `/menu`）为主；当前阶段仅保留接口骨架。
- **北向流量**：默认由 WAF/反向代理进入，服务端启用 `ProxyHeadersMiddleware` 以信任代理链头部。

## SLO 目标 (Day 1 基线)
- `GET /menu`：P95 ≤ 40 ms（缓存命中后常态 < 20 ms）。
- `POST /orders`：P95 ≤ 200 ms，业务失败率 < 0.1%，确保幂等写入。
- `POST /payments/notify/wechat`：P95 ≤ 120 ms，需支持重复回调。
- 商家端 WebSocket：心跳延迟 ≤ 2 s，断线重连 ≤ 5 s 内恢复订阅。
- 日常可用性：核心 API ≥ 99.9%，指标上报延迟 ≤ 60 s。

## 监控与健康检查
- `GET /healthz`：返回服务状态，供负载均衡与 K3s readiness 探针使用。
- `GET /metrics`：开启 `PROMETHEUS_ENABLED=true` 后输出 Prometheus 指标；禁用时返回 404，以避免暴露。
- 日志：结构化 JSON，默认写入 STDOUT，携带 `trace_id`、`path`，便于集中日志平台聚合。

## 基础防护
- **CORS**：`ALLOWED_ORIGINS` 控制跨域来源，默认包含本地前端 (`localhost:3000/5173`)。
- **限流策略**：SlowAPI 全局 300 次/分钟，并针对 `/api/v1/orders`、`/api/v1/payments/notify/wechat`、`/api/v1/products/{id}/want` 设定更严限额，初期防止压测或恶意请求。
- **代理信任**：当 `WAF_TRUST_PROXY=true` 时，服务解析 `X-Forwarded-*`，保证真实客户端 IP 进入审计与限流判定。

## 启动校验清单
1. `cp .env.example .env` 并按环境补齐敏感变量。
2. `.venv/Scripts/python -m pip install -r requirements-dev.txt` 安装依赖。
3. `make dev` 或 `docker compose up -d --build` 启动；确认日志输出包含 `trace_id`。
4. 访问 `http://localhost:8000/healthz` 返回 `{"status": "ok"}`。
5. 若开启 Prometheus，确认 `http://localhost:8000/metrics` 可抓取指标。
