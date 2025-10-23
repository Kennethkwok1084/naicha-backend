# M6W1 K3s 压测环境部署指南

> 目标：将 naicha-backend 打包并部署到 K3s 测试机进行压测  
> 更新时间：2025-10-22  
> 负责人：填写你的名字

---

## 🎯 部署流程概览

```
本地构建 → 推送镜像 → K3s 部署 → 环境验证 → 执行压测 → 收集结果
```

**预计耗时**：30-45 分钟（首次），10-15 分钟（后续）

---

## 📋 前置依赖检查

### 1. 本地工具

```bash
# 检查 Docker
docker --version  # >= 20.10

# 检查 kubectl
kubectl version --client  # >= 1.25

# 检查 Python 环境
python --version  # >= 3.11
pip list | grep -E "locust|websockets"
```

### 2. K3s 集群访问

```bash
# 检查 kubeconfig
export KUBECONFIG=/path/to/k3s.yaml
kubectl get nodes

# 预期输出：
# NAME           STATUS   ROLE                  AGE   VERSION
# k3s-staging    Ready    control-plane,master  30d   v1.28.x
```

### 3. 镜像仓库凭据

```bash
# 如使用 GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# 或使用私有仓库
docker login your-registry.com
```

---

## 🔨 步骤 1：构建和推送镜像

### 1.1 构建优化镜像

```bash
# 设置镜像标签（建议使用 Git commit hash）
export IMAGE_TAG=$(git rev-parse --short HEAD)
export IMAGE_REPO="ghcr.io/kennethkwok1084/naicha-backend"  # 替换为你的仓库

# 构建多阶段镜像（自动优化大小）
docker build \
  -f infra/docker/app.Dockerfile \
  -t ${IMAGE_REPO}:${IMAGE_TAG} \
  -t ${IMAGE_REPO}:staging \
  .

# 检查镜像大小（目标 < 500MB）
docker images ${IMAGE_REPO}:${IMAGE_TAG}
```

**优化建议**：
- ✅ 已使用多阶段构建（builder + runtime）
- ✅ 已使用 slim 基础镜像（python:3.11-slim）
- ✅ 已清理 apt 缓存
- 🔧 如需进一步优化，可添加 `.dockerignore`

### 1.2 创建 .dockerignore（如不存在）

```bash
cat > .dockerignore << 'EOF'
**/__pycache__
**/*.pyc
**/*.pyo
**/*.pyd
.pytest_cache
.coverage
htmlcov
*.log
.env
.env.*
!.env.example
perf_results/
doc/
tests/
infra/k8s/
infra/k3s/
infra/perf/
.git
.gitignore
README.md
*.md
Makefile
EOF
```

### 1.3 推送镜像

```bash
# 推送带版本号的镜像
docker push ${IMAGE_REPO}:${IMAGE_TAG}

# 推送 staging 标签（用于 Kustomize）
docker push ${IMAGE_REPO}:staging

# 验证推送成功
docker pull ${IMAGE_REPO}:staging
```

---

## ☸️ 步骤 2：准备 K3s 配置

### 2.1 创建命名空间

```bash
kubectl create namespace naicha-staging --dry-run=client -o yaml | kubectl apply -f -
```

### 2.2 准备 Secrets

#### a) 创建 API 环境变量 Secret

```bash
# 复制模板
cp .env.example infra/k3s/secrets/naicha-api-secrets.env

# 编辑配置（重要！填写真实值）
vim infra/k3s/secrets/naicha-api-secrets.env

# 示例配置：
# DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/naicha
# REDIS_URL=redis://redis:6379/0
# CELERY_BROKER_URL=redis://redis:6379/0
# SECRET_KEY=your-super-secret-key-min-32-chars
# PROMETHEUS_ENABLED=true
# MULTI_CATEGORY_ENABLED=true
# WANT_ENABLED=true

# 创建 Secret
kubectl create secret generic naicha-api-secrets \
  --from-env-file=infra/k3s/secrets/naicha-api-secrets.env \
  -n naicha-staging \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### b) 创建 PgBouncer 认证 Secret（如使用）

```bash
# 创建 userlist.txt
cat > infra/k3s/secrets/pgbouncer-userlist.txt << EOF
"naicha_user" "md5$(echo -n 'passwordnaicha_user' | md5sum | awk '{print $1}')"
EOF

kubectl create secret generic pgbouncer-auth \
  --from-file=userlist.txt=infra/k3s/secrets/pgbouncer-userlist.txt \
  -n naicha-staging \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 2.3 更新 Kustomize 配置

编辑 `infra/k3s/overlays/staging/kustomization.yaml`：

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: naicha-staging

resources:
  - ../../base

commonLabels:
  app.kubernetes.io/environment: staging
  app.kubernetes.io/part-of: naicha

images:
  - name: ghcr.io/your-org/naicha-backend
    newName: ghcr.io/kennethkwok1084/naicha-backend  # 替换为你的仓库
    newTag: staging

replicas:
  - name: naicha-api
    count: 2
  - name: naicha-worker
    count: 1

patchesStrategicMerge:
  - ingress-patch.yaml

# 如需调整资源限制（压测环境建议放宽）
patchesJson6902:
  - target:
      group: apps
      version: v1
      kind: Deployment
      name: naicha-api
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/memory
        value: 1Gi
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/cpu
        value: 1000m
```

---

## 🚀 步骤 3：部署到 K3s

### 3.1 校验配置

```bash
# Dry-run 检查（必须无错误）
kubectl apply -k infra/k3s/overlays/staging --dry-run=client

# 如有错误，检查：
# 1. Secret 是否已创建
# 2. 镜像名称是否正确
# 3. YAML 格式是否正确
```

### 3.2 执行部署

```bash
# 应用所有资源
kubectl apply -k infra/k3s/overlays/staging

# 监控部署进度
kubectl get pods -n naicha-staging -w

# 预期输出（等待所有 Pod 变为 Running）：
# NAME                            READY   STATUS    RESTARTS   AGE
# naicha-api-xxx-yyy              1/1     Running   0          30s
# naicha-api-xxx-zzz              1/1     Running   0          30s
# naicha-worker-xxx-yyy           1/1     Running   0          30s
# redis-0                         1/1     Running   0          30s
# pgbouncer-xxx-yyy               1/1     Running   0          30s
```

### 3.3 检查部署状态

```bash
# 查看 Deployment 状态
kubectl rollout status deployment/naicha-api -n naicha-staging
kubectl rollout status deployment/naicha-worker -n naicha-staging

# 查看 Pod 日志
kubectl logs -f deployment/naicha-api -n naicha-staging --tail=50

# 检查是否有错误日志
kubectl logs deployment/naicha-api -n naicha-staging | grep -i error
```

---

## ✅ 步骤 4：环境验证

### 4.1 健康检查

```bash
# 端口转发到本地
kubectl port-forward -n naicha-staging svc/naicha-api 8000:80 &

# 检查健康端点
curl http://localhost:8000/healthz
# 预期：{"status":"ok"}

# 检查 Prometheus 指标
curl http://localhost:8000/metrics | grep -E "order_create_total|payment_callback"

# 检查 API 文档
curl http://localhost:8000/docs
# 预期：返回 HTML（OpenAPI UI）
```

### 4.2 数据库连接验证

```bash
# 进入 API Pod
kubectl exec -it -n naicha-staging deployment/naicha-api -- /bin/bash

# 在 Pod 内执行
python -c "
from app.db.session import get_session
import asyncio
async def test():
    async for session in get_session():
        result = await session.execute('SELECT 1 as test')
        print(result.scalar())
        break
asyncio.run(test())
"
# 预期：输出 1
```

### 4.3 Redis 连接验证

```bash
# 检查 Redis 服务
kubectl exec -it -n naicha-staging statefulset/redis -- redis-cli ping
# 预期：PONG

# 检查 Celery Worker
kubectl logs -n naicha-staging deployment/naicha-worker --tail=20 | grep -i "ready"
# 预期：看到 "celery@xxx ready"
```

### 4.4 完整链路测试

```bash
# 获取管理员 Token（如果已有测试账号）
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 保存 Token
export TEST_TOKEN="Bearer eyJhbGc..."

# 测试创建订单
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: $TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-$(date +%s)" \
  -d '{
    "items": [{"product_id": 1, "quantity": 1}],
    "order_type": "pickup"
  }'

# 预期：返回订单详情
```

---

## 🔥 步骤 5：执行压测

### 5.1 配置压测环境变量

```bash
# 在本地或跳板机上配置
export PERF_BASE_URL="http://<K3s节点IP>:8000"  # 或通过 Ingress 域名
export PERF_USER_TOKEN="Bearer <your-token>"
export PERF_SECRET_KEY="<your-secret-key>"  # 与 K3s Secret 一致
export PERF_ADMIN_TOKEN="Bearer <admin-token>"  # WebSocket 测试需要

# 或使用端口转发（推荐，避免网络问题）
kubectl port-forward -n naicha-staging svc/naicha-api 8000:80 &
export PERF_BASE_URL="http://localhost:8000"
```

### 5.2 安装压测工具（如未安装）

```bash
pip install locust websockets
```

### 5.3 执行完整压测

```bash
# 方式 1：使用 Makefile
make perf-baseline

# 方式 2：手动执行
bash infra/perf/run_baseline.sh

# 预计耗时：5-10 分钟
```

### 5.4 实时监控（可选）

在压测期间，打开新终端监控：

```bash
# 监控 Pod CPU/内存
watch -n 2 kubectl top pods -n naicha-staging

# 监控日志
kubectl logs -f deployment/naicha-api -n naicha-staging

# 监控 Prometheus 指标
watch -n 5 'curl -s http://localhost:8000/metrics | grep -E "order_create_total|http_request_duration"'
```

---

## 📊 步骤 6：收集和分析结果

### 6.1 查看压测报告

```bash
# Locust HTML 报告
open perf_results/locust_100u_*.html
open perf_results/locust_200u_*.html
open perf_results/locust_500u_*.html

# WebSocket 测试日志
cat perf_results/ws_runner_*.log
```

### 6.2 自动填充基线文档

```bash
python infra/perf/parse_results.py \
  --input ./perf_results \
  --baseline ./doc/perf/perf-baseline.md

# 检查是否已填充
grep -A 5 "100 并发" doc/perf/perf-baseline.md
```

### 6.3 导出 Prometheus 快照

```bash
# 导出压测期间的指标
curl http://localhost:8000/metrics > perf_results/prometheus_snapshot_$(date +%Y%m%d_%H%M%S).txt

# 分析关键指标
grep -E "order_create_total|payment_callback_latency|http_request_duration" \
  perf_results/prometheus_snapshot_*.txt
```

### 6.4 归档结果

```bash
# 创建归档目录
mkdir -p doc/perf/reports/week1_$(date +%Y%m%d)

# 复制所有结果
cp -r perf_results/* doc/perf/reports/week1_$(date +%Y%m%d)/

# 记录环境信息
cat > doc/perf/reports/week1_$(date +%Y%m%d)/environment.txt << EOF
Git Commit: $(git rev-parse HEAD)
Git Branch: $(git branch --show-current)
Image Tag: staging
K3s Node: $(kubectl get nodes -o name)
Deployment Time: $(date)
API Replicas: 2
Worker Replicas: 1
EOF
```

---

## 🔍 故障排查

### 问题 1：Pod 一直处于 Pending 状态

```bash
# 检查原因
kubectl describe pod <pod-name> -n naicha-staging

# 常见原因：
# - 资源不足：调低 resources.requests
# - 镜像拉取失败：检查 imagePullSecrets
# - 存储卷不可用：检查 PVC 状态
```

### 问题 2：Pod CrashLoopBackOff

```bash
# 查看日志
kubectl logs <pod-name> -n naicha-staging --previous

# 常见原因：
# - 数据库连接失败：检查 DATABASE_URL
# - 缺少环境变量：检查 Secret 是否正确挂载
# - 端口冲突：检查 containerPort 配置
```

### 问题 3：压测时 502/503 错误

```bash
# 检查 Pod 是否健康
kubectl get pods -n naicha-staging

# 检查 Service 端点
kubectl get endpoints -n naicha-staging

# 检查资源使用
kubectl top pods -n naicha-staging

# 如果 CPU/内存达到上限，扩容：
kubectl scale deployment naicha-api --replicas=3 -n naicha-staging
```

### 问题 4：数据库连接池耗尽

```bash
# 检查 PgBouncer 日志（如使用）
kubectl logs deployment/pgbouncer -n naicha-staging

# 检查连接数
kubectl exec -it deployment/pgbouncer -n naicha-staging -- \
  psql -h localhost -p 6432 -U <user> -d pgbouncer -c "SHOW STATS;"

# 调整连接池（见 doc/perf/pool-config-diff.md）
```

### 问题 5：WebSocket 测试连接失败

```bash
# 检查 Token 格式
echo $PERF_ADMIN_TOKEN | grep -q "Bearer" || echo "缺少 Bearer 前缀"

# 检查 WebSocket 路由
kubectl logs deployment/naicha-api -n naicha-staging | grep -i websocket

# 测试手动连接
wscat -c "ws://localhost:8000/ws/merchant?token=${PERF_ADMIN_TOKEN#Bearer }"
```

---

## 📋 验收清单

完成以下所有项后，压测环境即为就绪：

### 部署验收
- [ ] 镜像构建成功且 < 500MB
- [ ] 镜像已推送到仓库
- [ ] 所有 Pod 状态为 Running
- [ ] `/healthz` 返回 200
- [ ] `/metrics` 返回 Prometheus 指标
- [ ] 手动创建订单成功

### 压测验收
- [ ] Locust 100/200/500 并发压测完成
- [ ] WebSocket 200 连接测试完成
- [ ] `doc/perf/perf-baseline.md` 已自动填充
- [ ] 所有关键接口 P95 达标（见 SLO）
- [ ] 错误率 < 1%
- [ ] HTML 报告已归档到 `doc/perf/reports/`

### 监控验收
- [ ] Prometheus 指标全部采集
- [ ] 压测期间无 Pod 重启
- [ ] 资源使用率 < 80%（CPU/内存）
- [ ] 数据库连接数 < 70%

---

## 🔄 更新和回滚

### 更新应用

```bash
# 构建新镜像
export IMAGE_TAG=$(git rev-parse --short HEAD)
docker build -f infra/docker/app.Dockerfile -t ${IMAGE_REPO}:${IMAGE_TAG} .
docker push ${IMAGE_REPO}:${IMAGE_TAG}

# 更新 Deployment
kubectl set image deployment/naicha-api \
  naicha-api=${IMAGE_REPO}:${IMAGE_TAG} \
  -n naicha-staging

# 监控滚动更新
kubectl rollout status deployment/naicha-api -n naicha-staging
```

### 回滚到上一版本

```bash
# 查看历史版本
kubectl rollout history deployment/naicha-api -n naicha-staging

# 回滚到上一版本
kubectl rollout undo deployment/naicha-api -n naicha-staging

# 回滚到特定版本
kubectl rollout undo deployment/naicha-api --to-revision=2 -n naicha-staging
```

### 完全清理环境

```bash
# 删除所有资源
kubectl delete -k infra/k3s/overlays/staging

# 删除命名空间（慎用！）
kubectl delete namespace naicha-staging

# 清理本地镜像
docker rmi ${IMAGE_REPO}:staging
```

---

## 📚 相关文档

- **压测指南**：`doc/perf/week1-guide.md`
- **快速开始**：`doc/perf/QUICKSTART.md`
- **环境验收**：`doc/perf/staging-checklist.md`
- **配置优化**：`doc/perf/pool-config-diff.md`
- **K3s 部署说明**：`infra/k3s/README.md`
- **M6 规划**：`doc/m6-plan-review.md`

---

## ✅ 完成标志

当你完成以下所有步骤，即可开始正式的 Week1 压测任务：

1. ✅ 镜像已构建并推送到仓库
2. ✅ K3s staging 环境部署成功
3. ✅ 环境验证通过（健康检查、数据库、Redis）
4. ✅ 压测环境变量已配置
5. ✅ 执行了一次完整压测并收集结果
6. ✅ `doc/perf/perf-baseline.md` 已填充

**接下来**：根据压测结果进行性能优化，详见 `doc/perf/pool-config-diff.md` 和 M6 Week1 计划。

---

**祝压测顺利！** 🚀
