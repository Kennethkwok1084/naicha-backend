# 部署资产概览

- `docker/app.Dockerfile`：多阶段构建，使用独立虚拟环境打包运行时依赖，默认暴露 `8000` 端口并以 `uvicorn` 启动。
- `docker/docker-compose.dev.yml`：开发/集成环境所需的基础编排，随附 PostgreSQL 服务，便于本地模拟。
- `k8s/deployment.yaml` / `k8s/service.yaml`：面向 K3s 的首版 Deployment 与 Service 模板，预留镜像拉取凭证与 Secret 引用，便于集群上线前逐步完善副本数与资源配置。

> 后续请在 build pipeline 中产出 `ghcr.io/<org>/naicha-backend:<tag>` 镜像并同步更新 `deployment.yaml` 中的镜像标签；同时在集群侧补充 `naicha-api-secrets` 及 `ghcr-pull-token`。
