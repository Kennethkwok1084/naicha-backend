# 部署资产概览

- `docker/app.Dockerfile`：多阶段构建，使用独立虚拟环境打包运行时依赖，默认暴露 `8000` 端口并以 `uvicorn` 启动。
- `docker/docker-compose.dev.yml`：开发/集成环境所需的基础编排，随附 PostgreSQL 服务，便于本地模拟。
- `k8s/deployment.yaml` / `k8s/service.yaml`：面向 K3s 的首版 Deployment 与 Service 模板，预留镜像拉取凭证与 Secret 引用，便于集群上线前逐步完善副本数与资源配置。
- `k8s/worker-deployment.yaml`：Celery Worker 进程的 Deployment 模板，复用应用镜像并以 `celery -A app.workers.celery_app:celery_app worker` 启动，支持水平扩展后台任务消费能力。

> 后续请在 build pipeline 中产出 `ghcr.io/<org>/naicha-backend:<tag>` 镜像并同步更新 `deployment.yaml` 中的镜像标签；同时在集群侧补充 `naicha-api-secrets` 及 `ghcr-pull-token`。

## 生产部署前置步骤

1. **创建密钥**：将所有敏感配置写入 K8s Secret（示例命令，文件需本地保存且勿入库）：
   ```bash
   kubectl create secret generic naicha-api-secrets \
     --from-literal=SECRET_KEY=<random> \
     --from-literal=DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/naicha \
     --from-literal=DATABASE_PROXY_URL=postgresql+asyncpg://user:pass@pgbouncer:6432/naicha \
     --from-literal=CELERY_BROKER_URL=redis://redis:6379/0 \
     --from-literal=CELERY_RESULT_BACKEND=redis://redis:6379/1 \
     --from-literal=WS_BROADCAST_URL=redis://redis:6379/0 \
     --from-literal=PRINTER_WEBHOOK_URL=https://printer.example.com/webhook \
     --from-literal=PRINTER_WEBHOOK_TOKEN=<token>
   ```
   可按环境需要追加其余变量（JWT 过期时间、观测开关等）。

2. **部署 Redis / PgBouncer**：确保队列与数据库代理服务在集群内可达，或在 `CELERY_*`、`DATABASE_PROXY_URL` 中指向托管实例。

3. **应用清单**：分别部署 API 与 Worker：
   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   kubectl apply -f k8s/worker-deployment.yaml
   ```

4. **滚动更新**：发布新版本时，先更新镜像标签，再执行：
   ```bash
   kubectl rollout restart deployment naicha-api
   kubectl rollout restart deployment naicha-worker
   ```
